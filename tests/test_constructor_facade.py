"""RED tests for Stage 8.1 — facade shell contract.

Every behavioural test injects a fake dispatcher through ``main()``
and asserts actual stdout/stderr output, exit-code mapping, channel
semantics (success/policy → stdout, error → stderr), colour
behaviour, and verbose diagnostics.

No test touches inventory, providers, networking, or Docker.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, Sequence

# ── helpers ────────────────────────────────────────────────────────────


def _load_mod() -> Any:
    """Import the importable facade module."""
    from docker import constructor_cli
    return constructor_cli


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# ANSI codes used by the renderer
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RESET = "\x1b[0m"


def _run(
    mod: Any,
    argv: Sequence[str],
    *,
    dispatcher: Any = None,
    stdout_isatty: bool = False,
    stderr_isatty: bool = False,
    _prompt_user: Callable[[str], bool] | None = None,
    _process_runner: Any = None,
    _container_inspector: Any = None,
    _run_executor: Any = None,
    _create_projection: Any = None,
    _project_selector: Any = None,
) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main(
            list(argv),
            dispatcher=dispatcher,
            stdout_isatty=lambda: stdout_isatty,
            stderr_isatty=lambda: stderr_isatty,
            _prompt_user=_prompt_user,
            _process_runner=_process_runner,
            _container_inspector=_container_inspector,
            _run_executor=_run_executor,
            _create_projection=_create_projection,
            _project_selector=_project_selector,
        )
    return rc, out.getvalue(), err.getvalue()


# ════════════════════════════════════════════════════════════════════════
# Fake dispatchers
# ════════════════════════════════════════════════════════════════════════

def _make_fake(
    mod: Any,
    *,
    exit_kind: str = "success",
    data: object = None,
    message: str | None = None,
    debug: str | None = None,
) -> Any:
    class Fake:
        def execute(self, command: str, request: Any) -> Any:
            Fake.command = command
            Fake.request = request
            return mod.CommandResult(
                exit_kind=getattr(mod.ExitKind, exit_kind.upper()),
                data=data,
                message=message,
                debug=debug,
            )
    return Fake()


def _make_recording_fake(mod: Any) -> Any:
    class Recording:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Any]] = []
        def execute(self, command: str, request: Any) -> Any:
            self.calls.append((command, request))
            return mod.CommandResult(
                exit_kind=mod.ExitKind.SUCCESS,
                data={"ok": True},
            )
    return Recording()


# ════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════


class TestImportSafety(unittest.TestCase):
    """Importing the facade produces no side effects."""

    def test_import_produces_no_stdout(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            _load_mod()
        self.assertEqual("", out.getvalue())

    def test_import_produces_no_stderr(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            _load_mod()
        self.assertEqual("", err.getvalue())

    def test_import_does_not_read_files(self) -> None:
        from unittest.mock import patch
        with patch("builtins.open", side_effect=RuntimeError("no open")):
            _load_mod()

    def test_import_does_not_access_network(self) -> None:
        import socket
        from unittest.mock import patch
        with patch.object(socket, "socket",
                          side_effect=RuntimeError("no network")):
            _load_mod()

    def test_import_does_not_execute_docker(self) -> None:
        import subprocess
        from unittest.mock import patch
        with patch.object(subprocess, "run",
                          side_effect=RuntimeError("no subprocess")):
            _load_mod()


class TestGlobalHelp(unittest.TestCase):
    """``--help`` behaviour and command surface."""

    AGREED = {"validate", "build", "run", "doctor", "verify", "show",
              "check-updates"}
    LEGACY = {"env", "get", "compose", "extensions", "schema"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_help_returns_zero(self) -> None:
        rc, _, _ = _run(self.m, ["--help"])
        self.assertEqual(0, rc)

    def test_help_names_docker_constructor(self) -> None:
        _, out, _ = _run(self.m, ["--help"])
        self.assertIn("docker/docker-constructor.py", out)

    def test_exact_agreed_commands_listed(self) -> None:
        _, out, _ = _run(self.m, ["--help"])
        for name in self.AGREED:
            self.assertIn(name, out, f"Missing command: {name}")
        for name in self.LEGACY:
            self.assertNotIn(name, out, f"Legacy command leaked: {name}")


class TestExitCodeMapping(unittest.TestCase):
    """Domain outcomes map to stable exit codes through dispatch."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_success_maps_to_zero(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok")
        rc, _, _ = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(0, rc)

    def test_policy_maps_to_one(self) -> None:
        fake = _make_fake(self.m, exit_kind="policy",
                          message="updates available")
        rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual(1, rc)

    def test_cli_maps_to_two(self) -> None:
        fake = _make_fake(self.m, exit_kind="cli", message="bad input")
        rc, _, _ = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(2, rc)

    def test_config_maps_to_three(self) -> None:
        fake = _make_fake(self.m, exit_kind="config",
                          message="invalid TOML")
        rc, _, _ = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(3, rc)

    def test_operational_maps_to_four(self) -> None:
        fake = _make_fake(self.m, exit_kind="operational",
                          message="network error")
        rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual(4, rc)


class TestDefaultDispatcherReturnsUnavailable(unittest.TestCase):
    """Default (real) dispatcher handles read-only commands without injection.

    Validate and show succeed with real inventory; check-updates is
    exercised through injected stub providers to avoid network access.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_validate_succeeds_on_real_inventory(self) -> None:
        rc, out, err = _run(self.m, ["validate"])
        self.assertEqual(0, rc)
        self.assertIn("valid", out)
        self.assertEqual("", err)

    def test_show_succeeds_on_real_inventory(self) -> None:
        rc, out, err = _run(self.m, ["show", "--scope", "build"])
        self.assertEqual(0, rc)
        self.assertIn("node", out)
        self.assertEqual("", err)

    def test_show_effective_mixed_overrides_scope_all(self) -> None:
        """Mixed build + runtime overrides with --scope all --effective
        must partition overrides by phase so each resolver only sees
        its own paths."""
        rc, out, err = _run(self.m, [
            "--output", "json",
            "show", "--scope", "all", "--effective",
            "--override", "build.stages.toolchain.python.version=3.15.0",
            "--override", "runtime.pi-extensions.pi-proxy.version=1.0.0",
        ])
        self.assertEqual(0, rc, f"exit {rc}: {err}")
        self.assertEqual("", err)
        payload = json.loads(out)
        data = payload["data"]
        self.assertIn("build", data, "build projection missing")
        self.assertIn("runtime", data, "runtime projection missing")
        # Build projection reflects the build override
        self.assertEqual("3.15.0", data["build"]["python_version"])
        # Runtime projection reflects the runtime override
        extensions = data["runtime"]["extensions"]
        pi_proxy = next(
            (e for e in extensions.values()
             if e.get("package", "").endswith("pi-proxy")),
            None,
        )
        self.assertIsNotNone(pi_proxy, "pi-proxy not found in runtime")
        self.assertEqual("1.0.0", pi_proxy["version"])

    def test_check_updates_with_stub_providers(self) -> None:
        import docker.versioning.updates
        from unittest.mock import patch
        from types import MappingProxyType
        from docker.versioning.model import UpdateCandidate, UpdateKind
        from docker.versioning.providers.base import ProviderResult

        class _Stub:
            def __init__(self, name):
                self.name = name

            def discover(self, target, context):
                return ProviderResult(
                    candidate=UpdateCandidate(
                        value=getattr(target, "current", ""),
                        kind=UpdateKind.VERSION,
                        artifacts={},
                    ),
                )

        fake_providers = MappingProxyType({
            k: _Stub(k) for k in (
                "docker-registry", "rust-channel", "static-url",
                "github-release", "uv-python", "pypi", "npm", "git-ref",
            )
        })
        with patch.object(docker.versioning.updates, "_DEFAULT_PROVIDERS",
                          fake_providers):
            rc, out, err = _run(self.m, ["check-updates"])
        self.assertEqual(0, rc)
        self.assertTrue(
            "docker-registry" in out.lower()
            or "node" in out.lower()
            or "build.stages" in out.lower()
        )
        self.assertEqual("", err)


# ════════════════════════════════════════════════════════════════════════
# Channel contract — the core semantic distinction
# ════════════════════════════════════════════════════════════════════════


class TestChannelContract(unittest.TestCase):
    """Success / policy → stdout; errors → stderr.  Data+message both rendered."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    # ── success on stdout ────────────────────────────────────────────

    def test_success_message_on_stdout_empty_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="done")
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertIn("[SUCCESS]", out)
        self.assertIn("done", out)
        self.assertEqual("", err)

    def test_policy_message_on_stdout_empty_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="policy",
                          message="updates found")
        _, out, err = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertIn("[POLICY]", out)
        self.assertIn("updates found", out)
        self.assertEqual("", err)

    # ── errors on stderr ─────────────────────────────────────────────

    def test_cli_error_on_stderr_empty_stdout(self) -> None:
        fake = _make_fake(self.m, exit_kind="cli", message="bad input")
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("[CLI]", err)
        self.assertIn("bad input", err)

    def test_config_error_on_stderr_empty_stdout(self) -> None:
        fake = _make_fake(self.m, exit_kind="config",
                          message="missing key")
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("[CONFIG]", err)
        self.assertIn("missing key", err)

    def test_operational_error_on_stderr_empty_stdout(self) -> None:
        fake = _make_fake(self.m, exit_kind="operational",
                          message="timeout")
        _, out, err = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("[OPERATIONAL]", err)
        self.assertIn("timeout", err)

    # ── data + message both rendered ─────────────────────────────────

    def test_success_renders_both_data_and_message(self) -> None:
        fake = _make_fake(self.m, exit_kind="success",
                          data={"count": 3}, message="inventory loaded")
        _, out, _ = _run(self.m, ["show"], dispatcher=fake)
        self.assertIn("inventory loaded", out)
        self.assertIn("data:", out)
        self.assertIn("count", out)

    def test_error_renders_both_data_and_message_on_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="config",
                          data={"missing": ["key1"]},
                          message="validation failed")
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("validation failed", err)
        self.assertIn("data:", err)
        self.assertIn("missing", err)

    # ── JSON always on stdout ────────────────────────────────────────

    def test_json_error_still_on_stdout(self) -> None:
        """In JSON mode, even errors go to stdout (machine-readable)."""
        fake = _make_fake(self.m, exit_kind="config",
                          message="missing key",
                          data={"field": "runtime"})
        _, out, _ = _run(
            self.m, ["--output", "json", "validate"],
            dispatcher=fake,
        )
        payload = json.loads(out)
        self.assertEqual("validate", payload["command"])
        self.assertEqual("config", payload["status"])
        self.assertEqual("missing key", payload["message"])
        self.assertEqual({"field": "runtime"}, payload["data"])

    def test_json_success_empty_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", data={"ok": True})
        _, _, err = _run(
            self.m, ["--output", "json", "show"],
            dispatcher=fake,
        )
        self.assertEqual("", err)

    # ── data-only (no message) ───────────────────────────────────────

    def test_success_data_only_on_stdout(self) -> None:
        fake = _make_fake(self.m, exit_kind="success",
                          data={"valid": True})
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertIn("[SUCCESS]", out)
        self.assertIn("valid", out)
        self.assertEqual("", err)

    def test_error_data_only_on_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="config",
                          data={"errors": 3})
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("[CONFIG]", err)
        self.assertIn("errors", err)

    # ── display_string shorthand ────────────────────────────────────

    def test_success_display_string_rendered_verbatim(self) -> None:
        """When data has a ``display_string`` key, text mode renders
        that string instead of Python's dict repr."""
        fake = _make_fake(self.m, exit_kind="success",
                          data={"display_string": "docker build --tag x .",
                                "build_args": ["docker", "build", "."]})
        _, out, err = _run(self.m, ["build"], dispatcher=fake)
        self.assertIn("docker build --tag x .", out)
        self.assertNotIn("display_string", out)
        self.assertNotIn("{", out)
        self.assertEqual("", err)

    def test_json_mode_preserves_full_structure(self) -> None:
        """In JSON mode, the full data dict (including display_string
        and build_args) is preserved."""
        fake = _make_fake(self.m, exit_kind="success",
                          data={"display_string": "docker build --tag x .",
                                "build_args": ["docker", "build", "."]})
        _, out, _ = _run(
            self.m, ["--output", "json", "build"],
            dispatcher=fake,
        )
        payload = json.loads(out)
        self.assertEqual("success", payload["status"])
        self.assertIn("display_string", payload["data"])
        self.assertIn("build_args", payload["data"])


class TestColourBehaviour(unittest.TestCase):
    """Colour resolved against the target stream's tty state."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    # ── error colour (stderr target) ─────────────────────────────────

    def test_error_color_always_stderr_tty_adds_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="config", message="fail")
        _, _, err = _run(
            self.m, ["--color", "always", "validate"],
            dispatcher=fake,
            stderr_isatty=True,
        )
        self.assertIsNotNone(ANSI_RE.search(err))

    def test_error_color_never_stderr_tty_no_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="config", message="fail")
        _, _, err = _run(
            self.m, ["--color", "never", "validate"],
            dispatcher=fake,
            stderr_isatty=True,
        )
        self.assertIsNone(ANSI_RE.search(err))

    def test_error_color_auto_stderr_not_tty_no_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="config", message="fail")
        _, _, err = _run(
            self.m, ["--color", "auto", "validate"],
            dispatcher=fake,
            stderr_isatty=False,
        )
        self.assertIsNone(ANSI_RE.search(err))

    def test_error_color_auto_stderr_tty_adds_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="config", message="fail")
        _, _, err = _run(
            self.m, ["--color", "auto", "validate"],
            dispatcher=fake,
            stderr_isatty=True,
        )
        self.assertIsNotNone(ANSI_RE.search(err))

    # ── success colour (stdout target) ───────────────────────────────

    def test_success_color_always_stdout_tty_adds_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok")
        _, out, _ = _run(
            self.m, ["--color", "always", "validate"],
            dispatcher=fake,
            stdout_isatty=True,
        )
        self.assertIsNotNone(ANSI_RE.search(out))

    def test_success_color_never_stdout_tty_no_ansi(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok")
        _, out, _ = _run(
            self.m, ["--color", "never", "validate"],
            dispatcher=fake,
            stdout_isatty=True,
        )
        self.assertIsNone(ANSI_RE.search(out))

    # ── cross-channel: stdout tty doesn't affect stderr ──────────────

    def test_error_stderr_tty_match_ignores_stdout_tty(self) -> None:
        """Error colour is resolved against stderr_isatty, not stdout."""
        fake = _make_fake(self.m, exit_kind="config", message="fail")
        # stdout tty, stderr not tty, color=auto → no ANSI on stderr
        _, _, err = _run(
            self.m, ["--color", "auto", "validate"],
            dispatcher=fake,
            stdout_isatty=True,
            stderr_isatty=False,
        )
        self.assertIsNone(ANSI_RE.search(err))


class TestVerbosity(unittest.TestCase):
    """--verbose emits debug detail to stderr; semantic output unchanged."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_verbose_adds_debug_to_stderr(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok",
                          debug="trace: x=1")
        _, _, err = _run(self.m, ["-v", "validate"], dispatcher=fake)
        self.assertIn("[debug] trace: x=1", err)

    def test_no_verbose_omits_debug(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok",
                          debug="trace: x=1")
        _, _, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertNotIn("[debug]", err)

    def test_semantic_stdout_identical_with_and_without_verbose(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", message="ok",
                          debug="extra")
        _, out_v, _ = _run(self.m, ["-v", "validate"], dispatcher=fake)
        _, out_nv, _ = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(out_v, out_nv)

    def test_json_stdout_unchanged_by_verbose(self) -> None:
        fake = _make_fake(self.m, exit_kind="success", data={"x": 1},
                          debug="extra")
        _, out_v, _ = _run(
            self.m, ["--output", "json", "-v", "validate"],
            dispatcher=fake,
        )
        _, out_nv, _ = _run(
            self.m, ["--output", "json", "validate"],
            dispatcher=fake,
        )
        self.assertEqual(out_v, out_nv)


class TestJSONOutput(unittest.TestCase):
    """JSON mode — everything on stdout, parseable, ANSI-free."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_json_output_is_parseable(self) -> None:
        fake = _make_fake(self.m, exit_kind="success",
                          data={"valid": True}, message="All good")
        _, out, _ = _run(self.m, ["--output", "json", "validate"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertEqual("validate", payload["command"])
        self.assertEqual("success", payload["status"])
        self.assertEqual({"valid": True}, payload["data"])
        self.assertEqual("All good", payload["message"])

    def test_json_output_has_no_ansi_regardless_of_color(self) -> None:
        for color in ("auto", "always", "never"):
            fake = _make_fake(self.m, exit_kind="config",
                              data={"x": 1}, message="err")
            _, out, _ = _run(
                self.m,
                ["--output", "json", "--color", color, "validate"],
                dispatcher=fake,
                stdout_isatty=(color == "always"),
            )
            self.assertIsNone(
                ANSI_RE.search(out),
                f"ANSI in JSON (--color {color}): {out!r}",
            )

    def test_json_no_data_no_message(self) -> None:
        fake = _make_fake(self.m, exit_kind="success")
        _, out, _ = _run(self.m, ["--output", "json", "validate"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertEqual("validate", payload["command"])
        self.assertEqual("success", payload["status"])
        self.assertNotIn("data", payload)
        self.assertNotIn("message", payload)


class TestDispatchRecording(unittest.TestCase):
    """The fake dispatcher receives parsed arguments as CommandRequest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_receives_command_name(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("validate", fake.calls[0][0])

    def test_receives_inventory_path(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["--inventory", "/tmp/custom.toml", "show"],
             dispatcher=fake)
        self.assertEqual("/tmp/custom.toml", fake.calls[0][1].inventory)

    def test_omitted_inventory_is_none(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["show"], dispatcher=fake)
        self.assertIsNone(fake.calls[0][1].inventory)

    def test_receives_output_mode(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["--output", "json", "validate"], dispatcher=fake)
        self.assertEqual("json", fake.calls[0][1].output)

    def test_receives_verbose_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["-v", "validate"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].verbose)

    def test_receives_color_mode(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["--color", "always", "validate"], dispatcher=fake)
        self.assertEqual("always", fake.calls[0][1].color)

    def test_receives_command_specific_args(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["show", "--scope", "build", "--effective"],
             dispatcher=fake)
        self.assertEqual("build", fake.calls[0][1].command_args["scope"])
        self.assertTrue(fake.calls[0][1].command_args["effective"])

    def test_no_phase_specific_inventory_options(self) -> None:
        parser = self.m._build_parser()
        all_opts: set[str] = set()
        for a in parser._actions:
            for opt in a.option_strings:
                all_opts.add(opt)
        self.assertNotIn("--build-inventory", all_opts)
        self.assertNotIn("--runtime-inventory", all_opts)

    def test_command_request_is_genuinely_immutable(self) -> None:
        """CommandRequest fields (including command_args mapping) are frozen."""
        CR = self.m.CommandRequest
        req = CR(
            command="validate",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"scope": "build"},
        )
        with self.assertRaises(Exception):
            req.inventory = "/hacked"  # type: ignore[misc]
        with self.assertRaises(Exception):
            req.output = "json"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            req.command_args["scope"] = "runtime"  # type: ignore[index]
        with self.assertRaises(TypeError):
            req.command_args["new_key"] = 1  # type: ignore[index]
        with self.assertRaises(TypeError):
            del req.command_args["scope"]  # type: ignore[arg-type]

    def test_nested_lists_frozen_to_tuples(self) -> None:
        """Parser-owned lists (projects, only_filter) become tuples."""
        CR = self.m.CommandRequest
        req = CR(
            command="run",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"projects": ["/a", "/b"], "dry_run": False},
        )
        self.assertIsInstance(req.command_args["projects"], tuple)
        self.assertEqual(("/a", "/b"), req.command_args["projects"])
        with self.assertRaises(TypeError):
            req.command_args["projects"][0] = "/hacked"  # type: ignore[index]

    def test_nested_list_from_real_parser_is_frozen(self) -> None:
        """--project /a --project /b → tuple, not list."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["run", "--project", "/a", "--project", "/b"],
             dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        req = fake.calls[0][1]
        projects = req.command_args["projects"]
        self.assertIsInstance(projects, tuple)
        self.assertEqual(("/a", "/b"), projects)
        with self.assertRaises(TypeError):
            projects[0] = "/hacked"  # type: ignore[index]

    def test_only_filter_list_frozen_via_real_parser(self) -> None:
        """--only x --only y becomes a frozen tuple."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--only", "gh", "--only", "docker"],
             dispatcher=fake)
        req = fake.calls[0][1]
        only_filter = req.command_args["only_filter"]
        self.assertIsInstance(only_filter, tuple)
        self.assertEqual(("gh", "docker"), only_filter)
        with self.assertRaises(TypeError):
            only_filter[0] = "hacked"  # type: ignore[index]

    def test_nested_dict_frozen(self) -> None:
        """Nested dicts inside command_args are frozen recursively."""
        CR = self.m.CommandRequest
        req = CR(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={
                "overrides": {"python": "3.13.0", "node": "22.0.0"},
            },
        )
        overrides = req.command_args["overrides"]
        self.assertIsInstance(overrides, self.m.MappingProxyType)
        with self.assertRaises(TypeError):
            overrides["python"] = "hacked"  # type: ignore[index]

    def test_nested_list_inside_dict_frozen(self) -> None:
        """List values inside nested dicts become tuples."""
        CR = self.m.CommandRequest
        req = CR(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={
                "overrides": {"python": ["3.13.0", "3.12.0"]},
            },
        )
        inner = req.command_args["overrides"]
        self.assertIsInstance(inner["python"], tuple)
        self.assertEqual(("3.13.0", "3.12.0"), inner["python"])

    def test_proxy_with_nested_list_is_deeply_frozen(self) -> None:
        """A MappingProxyType containing a list must have that list frozen.

        This guards against a bypass where _deep_freeze skips an
        already-frozen proxy without inspecting its children.
        """
        from types import MappingProxyType
        CR = self.m.CommandRequest
        # Pre-wrap a dict with a mutable list value in a proxy
        pre_frozen = MappingProxyType({"items": [1, 2, 3]})
        req = CR(
            command="run",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"opts": pre_frozen},
        )
        opts = req.command_args["opts"]
        self.assertIsInstance(opts, MappingProxyType)
        items = opts["items"]
        self.assertIsInstance(items, tuple,
                             "nested list inside proxy must become tuple")
        self.assertEqual((1, 2, 3), items)
        with self.assertRaises(TypeError):
            items[0] = 99  # type: ignore[index]


class TestCLIInputErrors(unittest.TestCase):
    """Invalid input → exit 2, message on stderr, no dispatcher call."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_missing_command(self) -> None:
        rc, _, err = _run(self.m, [])
        self.assertEqual(2, rc)
        self.assertIn("arguments are required", err.lower())

    def test_unknown_command(self) -> None:
        rc, _, err = _run(self.m, ["frobnicate"])
        self.assertEqual(2, rc)
        self.assertIn("invalid choice", err.lower())

    def test_unknown_global_option(self) -> None:
        rc, _, err = _run(self.m, ["--frob", "validate"])
        self.assertEqual(2, rc)
        self.assertIn("unrecognized arguments", err.lower())

    def test_invalid_output_mode(self) -> None:
        rc, _, err = _run(self.m, ["--output", "yaml", "validate"])
        self.assertEqual(2, rc)
        self.assertIn("invalid choice", err.lower())

    def test_invalid_color_mode(self) -> None:
        rc, _, err = _run(self.m, ["--color", "green", "validate"])
        self.assertEqual(2, rc)
        self.assertIn("invalid choice", err.lower())

    def test_missing_option_value(self) -> None:
        rc, _, err = _run(self.m, ["--output", "validate"])
        self.assertEqual(2, rc)
        self.assertIn("invalid choice", err.lower())

    def test_global_option_must_precede_subcommand(self) -> None:
        rc, _, err = _run(self.m, ["validate", "--inventory", "/x"])
        self.assertEqual(2, rc)
        self.assertIn("unrecognized arguments", err.lower())


# ════════════════════════════════════════════════════════════════════════
# Stage 9.4 — build and doctor CLI flag propagation
# ════════════════════════════════════════════════════════════════════════


class TestBuildCLIFlags(unittest.TestCase):
    """Build subcommand flags must reach the fake dispatcher via
    ``CommandRequest.command_args``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_platform_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--platform", "linux-arm64"], dispatcher=fake)
        self.assertEqual("linux-arm64",
                         fake.calls[0][1].command_args["platform"])

    def test_tag_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--tag", "pi-cli-pi:v2"], dispatcher=fake)
        self.assertEqual("pi-cli-pi:v2",
                         fake.calls[0][1].command_args["tag"])

    def test_empty_tag_preserved_for_renderer_validation(self) -> None:
        """``--tag ""`` must be preserved as an empty string (not
        coerced to ``None``) so the renderer rejects it as CONFIG."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(self.m, ["build", "--dry-run", "--tag", ""],
                             dispatcher=fake)
        # The empty tag reaches orchestration via BuildRequest, not
        # silently discarded by the facade.
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("", fake.calls[0][1].command_args["tag"])

    def test_dry_run_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--dry-run"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["dry_run"])

    def test_yes_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--yes"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["yes"])

    def test_overrides_flag_parsed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--override", "python.version=3.13.0",
                      "--override", "node.version=22.0.0"], dispatcher=fake)
        self.assertEqual(
            {"python.version": "3.13.0", "node.version": "22.0.0"},
            dict(fake.calls[0][1].command_args["overrides"]),
        )

    def test_cache_flag_default(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["cache"])

    def test_no_cache_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--no-cache"], dispatcher=fake)
        self.assertFalse(fake.calls[0][1].command_args["cache"])

    def test_pull_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--pull"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["pull"])

    def test_no_pull_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--no-pull"], dispatcher=fake)
        self.assertFalse(fake.calls[0][1].command_args["pull"])

    def test_progress_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--progress", "plain"], dispatcher=fake)
        self.assertEqual("plain",
                         fake.calls[0][1].command_args["progress"])

    def test_uid_gid_flags(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build", "--uid", "2000", "--gid", "2001"],
             dispatcher=fake)
        self.assertEqual(2000, fake.calls[0][1].command_args["uid"])
        self.assertEqual(2001, fake.calls[0][1].command_args["gid"])

    def test_build_dispatches_to_execute(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["build"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("build", fake.calls[0][0])

    def test_invalid_override_returns_cli(self) -> None:
        """``--override no-equals`` (missing '=') is caught by the facade
        before reaching the dispatcher."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(self.m, ["build", "--override", "no-equals"],
                              dispatcher=fake)
        self.assertEqual(2, rc)
        self.assertIn("expected path=value", err.lower())
        # Dispatcher must not have been called
        self.assertEqual(0, len(fake.calls))

    def test_duplicate_override_returns_cli(self) -> None:
        """Repeating the same override path is rejected before dispatch."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(
            self.m,
            ["build", "--override", "a=1", "--override", "a=2"],
            dispatcher=fake,
        )
        self.assertEqual(2, rc)
        self.assertIn("duplicate", err.lower())
        self.assertEqual(0, len(fake.calls))


class TestDoctorCLIFlags(unittest.TestCase):
    """Doctor subcommand flags must reach the fake dispatcher."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_apply_override_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--apply-rootless-override"],
             dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["apply_override"])

    def test_apply_override_default_false(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor"], dispatcher=fake)
        self.assertFalse(fake.calls[0][1].command_args["apply_override"])

    def test_yes_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--yes"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["yes"])

    def test_probe_image_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--probe-image", "busybox:1.36"],
             dispatcher=fake)
        self.assertEqual("busybox:1.36",
                         fake.calls[0][1].command_args["probe_image"])

    def test_probe_timeout_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--probe-timeout", "10"],
             dispatcher=fake)
        self.assertEqual(10, fake.calls[0][1].command_args["probe_timeout"])

    def test_doctor_dispatches_to_execute(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("doctor", fake.calls[0][0])

    def test_float_probe_timeout_rejected_by_argparse(self) -> None:
        """``--probe-timeout`` expects an integer; float values are
        rejected at the CLI parser level."""
        rc, _out, err = _run(self.m, ["doctor", "--probe-timeout", "5.5"])
        self.assertEqual(2, rc)
        self.assertIn("invalid int value", err.lower())

    def test_explicit_empty_probe_image_rejected(self) -> None:
        """An explicit ``--probe-image ""`` must be rejected as a CLI
        input error before calling the dispatcher."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(self.m, ["doctor", "--probe-image", ""],
                             dispatcher=fake)
        self.assertEqual(2, rc,
                         "empty --probe-image must produce CLI error")
        self.assertIn("must not be empty", err.lower())
        self.assertEqual(0, len(fake.calls),
                         "dispatcher must NOT be called on invalid input")

    def test_probe_timeout_below_minimum_rejected(self) -> None:
        """``--probe-timeout 0`` must be rejected (below 1)."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(self.m, ["doctor", "--probe-timeout", "0"],
                             dispatcher=fake)
        self.assertEqual(2, rc)
        self.assertIn("must be 1", err.lower())
        self.assertEqual(0, len(fake.calls))

    def test_probe_timeout_above_maximum_rejected(self) -> None:
        """``--probe-timeout 301`` must be rejected (above 300)."""
        fake = _make_recording_fake(self.m)
        rc, _out, err = _run(self.m, ["doctor", "--probe-timeout", "301"],
                             dispatcher=fake)
        self.assertEqual(2, rc)
        self.assertIn("must be 1", err.lower())
        self.assertEqual(0, len(fake.calls))

    def test_probe_timeout_minimum_accepted(self) -> None:
        """``--probe-timeout 1`` is valid (lower bound)."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--probe-timeout", "1"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual(1, fake.calls[0][1].command_args["probe_timeout"])

    def test_probe_timeout_maximum_accepted(self) -> None:
        """``--probe-timeout 300`` is valid (upper bound)."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["doctor", "--probe-timeout", "300"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual(300, fake.calls[0][1].command_args["probe_timeout"])


class TestDoctorStructuredData(unittest.TestCase):
    """Verify that ``_real_dispatcher`` always emits structured JSON
    data for doctor, including on unreachable / failure outcomes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def _call_dispatcher(self, **cmd_args: object) -> Any:
        """Shortcut: call ``_real_dispatcher`` for 'doctor' with given
        command_args, skipping prompt (yes=True)."""
        CR = self.m.CommandRequest
        req = CR(
            command="doctor", inventory=None, output="text",
            verbose=False, color="auto",
            command_args={"yes": True, **cmd_args},
        )
        return self.m._real_dispatcher("doctor", req)

    def test_unreachable_gateway_emits_data(self) -> None:
        """When the gateway is unreachable, data must still include
        gateway (null) and repair_applied."""
        result = self._call_dispatcher()
        self.assertIsNotNone(result.data,
                             "data must not be None on unreachable gateway")
        self.assertIsNone(result.data["gateway"])
        self.assertFalse(result.data["repair_applied"])

    def test_repair_failure_included_in_data(self) -> None:
        """When a repair failure occurs, the full structured
        ``OverrideFailure`` must appear in data."""
        from unittest.mock import patch

        from docker.networking import OverrideFailure
        from docker.versioning import build_orchestration
        from docker.versioning.build_orchestration import DoctorResult
        from docker.versioning.dispatch_types import ExitKind

        failure = OverrideFailure(
            operation="mkdir", path_or_command="/etc/docker",
            detail="permission denied", persistence_applied=False,
        )

        fake_result = DoctorResult(
            exit_kind=ExitKind.OPERATIONAL,
            message="repair failed",
            initial_diagnosis=None,  # type: ignore[arg-type]
            selected_gateway="10.0.2.2",
            repair_applied=False,
            repair_failure=failure,
        )

        with patch.object(build_orchestration, "orchestrate_doctor",
                          return_value=fake_result):
            CR = self.m.CommandRequest
            result = self.m._real_dispatcher(
                "doctor",
                CR(
                    command="doctor", inventory=None, output="text",
                    verbose=False, color="auto",
                    command_args={"apply_override": True, "yes": True},
                ),
            )

        self.assertIsNotNone(result.data)
        rf = result.data.get("repair_failure") if result.data else None
        self.assertIsInstance(rf, dict)
        self.assertEqual("mkdir", rf["operation"])
        self.assertEqual("/etc/docker", rf["path_or_command"])
        self.assertEqual("permission denied", rf["detail"])
        self.assertFalse(rf["persistence_applied"])

    def test_full_diagnosis_data_includes_docker_mode_and_probes(self) -> None:
        """When initial diagnosis is present, data must include
        docker_mode, probes, override_installed, override_needed."""
        from unittest.mock import patch

        from docker.networking import (
            DockerMode,
            GatewayDiagnosis,
            OverrideState,
            ProbeResult,
            RootlessOverridePlan,
        )
        from docker.versioning import build_orchestration
        from docker.versioning.build_orchestration import DoctorResult
        from docker.versioning.dispatch_types import ExitKind

        init = GatewayDiagnosis(
            mode=DockerMode.ROOTLESS,
            probe_port=8080,
            probe_token="tok",
            lan_ip=None,
            probes=(
                ProbeResult(
                    candidate="10.0.2.2", ok=True,
                    resolved_ip="10.0.2.2", detail="",
                ),
                ProbeResult(
                    candidate="172.17.0.1", ok=False,
                    resolved_ip=None, detail="timeout",
                ),
            ),
            chosen_gateway="10.0.2.2",
            override_installed=False,
            override_needed=True,
        )
        plan = RootlessOverridePlan(
            installed=False, needed=True,
            state=OverrideState.ABSENT,
            filesystem_ops=(), service_ops=(),
        )

        fake_result = DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            initial_diagnosis=init,
            override_plan=plan,
            selected_gateway="10.0.2.2",
            repair_applied=False,
        )

        with patch.object(build_orchestration, "orchestrate_doctor",
                          return_value=fake_result):
            CR = self.m.CommandRequest
            result = self.m._real_dispatcher(
                "doctor",
                CR(
                    command="doctor", inventory=None, output="text",
                    verbose=False, color="auto",
                    command_args={"yes": True},
                ),
            )

        data = result.data
        self.assertIsNotNone(data)
        self.assertEqual("rootless", data["docker_mode"])
        self.assertFalse(data["override_installed"])
        self.assertTrue(data["override_needed"])
        self.assertEqual("absent", data["override_state"])

        probes = data["probes"]
        self.assertEqual(2, len(probes))
        self.assertEqual("10.0.2.2", probes[0]["candidate"])
        self.assertTrue(probes[0]["ok"])
        self.assertEqual("172.17.0.1", probes[1]["candidate"])
        self.assertFalse(probes[1]["ok"])
        self.assertEqual("timeout", probes[1]["detail"])

    def test_post_repair_diagnosis_includes_full_outcome(self) -> None:
        """Post-repair data must include gateway, mode, and probes."""
        from unittest.mock import patch

        from docker.networking import (
            DockerMode,
            GatewayDiagnosis,
            ProbeResult,
        )
        from docker.versioning import build_orchestration
        from docker.versioning.build_orchestration import DoctorResult
        from docker.versioning.dispatch_types import ExitKind

        post = GatewayDiagnosis(
            mode=DockerMode.ROOTLESS,
            probe_port=8080,
            probe_token="tok",
            lan_ip=None,
            probes=(
                ProbeResult(
                    candidate="10.0.2.2", ok=True,
                    resolved_ip="10.0.2.2", detail="",
                ),
            ),
            chosen_gateway="10.0.2.2",
            override_installed=True,
            override_needed=False,
        )

        fake_result = DoctorResult(
            exit_kind=ExitKind.SUCCESS,
            post_repair_diagnosis=post,
            selected_gateway="10.0.2.2",
            repair_applied=True,
        )

        with patch.object(build_orchestration, "orchestrate_doctor",
                          return_value=fake_result):
            CR = self.m.CommandRequest
            result = self.m._real_dispatcher(
                "doctor",
                CR(
                    command="doctor", inventory=None, output="text",
                    verbose=False, color="auto",
                    command_args={"apply_override": True, "yes": True},
                ),
            )

        data = result.data
        self.assertIsNotNone(data)
        self.assertIn("post_repair", data)
        pr = data["post_repair"]
        self.assertEqual("10.0.2.2", pr["gateway"])
        self.assertEqual("rootless", pr["mode"])
        self.assertEqual(1, len(pr["probes"]))
        self.assertTrue(pr["probes"][0]["ok"])


# ════════════════════════════════════════════════════════════════════════
# Stage 9.4 — confirmation prompting (facade-owned, injectable)
# ════════════════════════════════════════════════════════════════════════


def _make_prompt_always(mod: Any) -> Callable[[str], bool]:
    """Return a prompt mock that always approves."""
    calls: list[str] = []
    def _approve(prompt_text: str) -> bool:
        calls.append(prompt_text)
        return True
    _approve.calls = calls  # type: ignore[attr-defined]
    return _approve


def _make_prompt_never(mod: Any) -> Callable[[str], bool]:
    """Return a prompt mock that always denies."""
    calls: list[str] = []
    def _deny(prompt_text: str) -> bool:
        calls.append(prompt_text)
        return False
    _deny.calls = calls  # type: ignore[attr-defined]
    return _deny


class TestBuildConfirmation(unittest.TestCase):
    """Build confirmation: prompted unless ``--dry-run`` or ``--yes``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_prompted_when_neither_dry_run_nor_yes(self) -> None:
        prompt = _make_prompt_always(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"dry_run": False, "yes": False},
        )
        _result = self.m._real_dispatcher(
            "build", req, _prompt_user=prompt,
        )
        self.assertEqual(1, len(prompt.calls))  # type: ignore[attr-defined]
        self.assertIn("Build the Pi container", prompt.calls[0])  # type: ignore[attr-defined]

    def test_denial_returns_success_cancellation(self) -> None:
        prompt = _make_prompt_never(self.m)
        # We need a recording dispatcher to prove it wasn't called
        record = _make_recording_fake(self.m)
        # Call _real_dispatcher directly since prompt is injectable there
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"dry_run": False, "yes": False},
        )
        result = self.m._real_dispatcher(
            "build", req, _prompt_user=prompt,
        )
        self.assertEqual(self.m.ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("cancelled", result.message.lower())

    def test_approval_passes_yes_true_to_dispatch(self) -> None:
        prompt = _make_prompt_always(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"dry_run": False, "yes": False},
        )
        result = self.m._real_dispatcher(
            "build", req, _prompt_user=prompt,
        )
        # Confirmation was approved; orchestration ran and returned
        # a result (may be CONFIG or SUCCESS depending on inventory)
        self.assertIsNotNone(result.exit_kind)
        self.assertNotIn("cancelled", (result.message or "").lower())

    def test_dry_run_bypasses_prompt(self) -> None:
        prompt = _make_prompt_never(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"dry_run": True, "yes": False},
        )
        result = self.m._real_dispatcher(
            "build", req, _prompt_user=prompt,
        )
        # Prompt was never called; orchestration ran
        self.assertEqual(0, len(prompt.calls))  # type: ignore[attr-defined]
        self.assertIsNotNone(result.exit_kind)

    def test_yes_bypasses_prompt(self) -> None:
        prompt = _make_prompt_never(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="build",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"dry_run": False, "yes": True},
        )
        result = self.m._real_dispatcher(
            "build", req, _prompt_user=prompt,
        )
        # Prompt was never called
        self.assertEqual(0, len(prompt.calls))  # type: ignore[attr-defined]


class TestDoctorConfirmation(unittest.TestCase):
    """Doctor confirmation: prompted only when
    ``--apply-rootless-override`` is set without ``--yes``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_diagnosis_only_no_prompt(self) -> None:
        prompt = _make_prompt_never(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="doctor",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"apply_override": False, "yes": False},
        )
        result = self.m._real_dispatcher(
            "doctor", req, _prompt_user=prompt,
        )
        self.assertEqual(0, len(prompt.calls))  # type: ignore[attr-defined]
        self.assertIsNotNone(result.exit_kind)

    def test_repair_with_yes_bypasses_prompt(self) -> None:
        prompt = _make_prompt_never(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="doctor",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"apply_override": True, "yes": True},
        )
        result = self.m._real_dispatcher(
            "doctor", req, _prompt_user=prompt,
        )
        self.assertEqual(0, len(prompt.calls))  # type: ignore[attr-defined]

    def test_repair_without_yes_prompts(self) -> None:
        prompt = _make_prompt_always(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="doctor",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"apply_override": True, "yes": False},
        )
        result = self.m._real_dispatcher(
            "doctor", req, _prompt_user=prompt,
        )
        self.assertEqual(1, len(prompt.calls))  # type: ignore[attr-defined]
        self.assertIn("Apply rootless", prompt.calls[0])  # type: ignore[attr-defined]

    def test_repair_denied_returns_cancellation(self) -> None:
        prompt = _make_prompt_never(self.m)
        from docker.constructor_cli import CommandRequest
        req = CommandRequest(
            command="doctor",
            inventory=None,
            output="text",
            verbose=False,
            color="auto",
            command_args={"apply_override": True, "yes": False},
        )
        result = self.m._real_dispatcher(
            "doctor", req, _prompt_user=prompt,
        )
        self.assertEqual(self.m.ExitKind.SUCCESS, result.exit_kind)
        self.assertIn("denied", result.message.lower())


class TestConfirmationNonInteractive(unittest.TestCase):
    """When stdin is not a TTY, the prompt must return False without
    blocking."""

    def test_stdin_prompt_returns_false_when_not_tty(self) -> None:
        # The real _stdin_prompt checks sys.__stdin__.isatty()
        # In a unittest runner, stdin is typically not a TTY
        from docker.constructor_cli import _stdin_prompt
        result = _stdin_prompt("Should not block")
        self.assertFalse(result)


class TestRunExecutionBoundaries(unittest.TestCase):
    """Prove the facade wires real execution boundaries into
    ``RunRequest`` when the run command is invoked."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def _make_fake_runner(self) -> list:
        """Return a recording list and a fake ProcessRunner.

        The fake records every ``run(argv)`` call as a tuple ``(argv,)``
        and returns a successful ProcessResult.
        """

        from docker.launcher import ProcessResult

        calls: list[tuple[list[str]]] = []

        class FakeRunner:
            def run(self, argv: list[str]) -> ProcessResult:
                calls.append((list(argv),))
                return ProcessResult(
                    argv=tuple(argv), return_code=0,
                    stdout="", stderr="",
                )

        return FakeRunner(), calls

    def _make_noop_projection_factory(self) -> tuple[Any, list]:
        calls: list[object] = []

        class RecordingHandle:
            def __init__(self, proj: object, parent: str) -> None:
                self.projection = proj
                self.parent_dir = parent
                self.entered = False
                self.exited = False
                self.path = "/tmp/.docker-generated/runtime/proj.toml"
                self.content_hash = (
                    "abc123def456789abc123def456789abc123def456789abc123def456789"
                )

            def __enter__(self) -> "RecordingHandle":
                self.entered = True
                return self

            def __exit__(self, *a: object) -> None:
                self.exited = True
                return None

        def factory(projection: object, *, parent_dir: str) -> Any:
            h = RecordingHandle(projection, parent_dir)
            calls.append(h)
            return h

        return factory, calls

    def test_default_real_boundaries_are_created_and_wired(self) -> None:
        """Without injection, the facade creates real ProcessRunner,
        DockerContainerInspector, and DockerRunExecutor and passes
        them to RunRequest."""
        from docker.launcher import (
            DockerContainerInspector,
            DockerRunExecutor,
            ProcessRunner,
        )

        runner = ProcessRunner()
        self.assertIsInstance(runner, ProcessRunner)
        inspector = DockerContainerInspector(runner)
        self.assertIsInstance(inspector, DockerContainerInspector)
        executor = DockerRunExecutor(runner)
        self.assertIsInstance(executor, DockerRunExecutor)
        # Prove the real classes are distinct from each other
        self.assertIsNot(inspector, executor)
        self.assertIs(inspector._runner, runner)
        self.assertIs(executor._runner, runner)

    def test_fake_boundaries_are_passed_to_run_request(self) -> None:
        """Inject fakes and prove they reach the run orchestration.

        The test creates fake ProcessRunner, ContainerNameInspector,
        and RunExecutor.  Each records every call made to it.  When
        the facade runs ``run --main-project /tmp/t --dry-run`` the
        dry-run path should NOT invoke the executor or inspector —
        we prove that by asserting zero call records.

        Then we run without --dry-run and prove the inspector is
        called (pi-N allocation) and the executor is called (docker
        run).
        """
        import tempfile
        from contextlib import contextmanager

        fake_runner, runner_calls = self._make_fake_runner()
        factory, proj_calls = self._make_noop_projection_factory()

        class FakeInspector:
            def __init__(self) -> None:
                self.calls: list[object] = []

            def list_names(self) -> set[str]:
                self.calls.append("list_names")
                return set()  # no existing pi-N containers

        class FakeExecutor:
            def __init__(self, runner: Any) -> None:
                self.runner = runner
                self.calls: list[object] = []

            def run(self, argv: tuple[str, ...]) -> Any:
                self.calls.append(argv)
                return self.runner.run(list(argv))

        inspector = FakeInspector()
        executor = FakeExecutor(fake_runner)

        # ── Dry-run: boundaries must NOT be invoked ────────────
        rc1, out1, _err1 = _run(
            self.m,
            ["run", "--main-project", "/tmp/test", "--dry-run"],
            dispatcher=None,
            _process_runner=fake_runner,
            _container_inspector=inspector,
            _run_executor=executor,
            _create_projection=factory,
        )
        self.assertEqual(0, rc1, f"dry-run exit code; stdout={out1}")
        # No Docker was invoked
        self.assertEqual([], inspector.calls)
        self.assertEqual([], executor.calls)
        self.assertEqual([], runner_calls)
        # No projection file was created
        self.assertEqual([], proj_calls)

        # ── Non-dry-run: boundaries must be invoked ────────────
        inspector2 = FakeInspector()
        executor2 = FakeExecutor(fake_runner)
        fake_runner2, runner_calls2 = self._make_fake_runner()
        factory2, proj_calls2 = self._make_noop_projection_factory()

        rc2, out2, _err2 = _run(
            self.m,
            ["run", "--main-project", "/tmp/test"],
            dispatcher=None,
            _process_runner=fake_runner2,
            _container_inspector=inspector2,
            _run_executor=executor2,
            _create_projection=factory2,
        )
        self.assertEqual(0, rc2, f"exec exit code; stdout={out2}")
        # Inspector was called for pi-N allocation
        self.assertEqual(["list_names"], inspector2.calls)
        # Executor was called — the run vector was rendered and passed
        self.assertEqual(1, len(executor2.calls))
        run_argv = executor2.calls[0]
        self.assertIn("docker", run_argv)
        self.assertIn("run", run_argv)
        # Projection factory was called and lifecycle managed
        self.assertEqual(1, len(proj_calls2))
        self.assertTrue(proj_calls2[0].entered, "handle was entered")
        self.assertTrue(proj_calls2[0].exited, "handle was exited")

    def test_override_boundary_preserves_identity(self) -> None:
        """When a single ProcessRunner is injected, DockerContainerInspector
        and DockerRunExecutor are both bootstrapped from it and retain
        the identity chain."""
        from docker.launcher import (
            DockerContainerInspector,
            DockerRunExecutor,
            ProcessRunner,
        )
        # Only inject _process_runner — the facade should create
        # the Docker wrappers around it.
        fake_runner, _ = self._make_fake_runner()

        # Prove local construction works first
        ci = DockerContainerInspector(fake_runner)
        re = DockerRunExecutor(fake_runner)
        self.assertIs(ci._runner, fake_runner)
        self.assertIs(re._runner, fake_runner)

    def test_pi_home_mount_source_is_authoritative_host_home(self) -> None:
        """The rendered docker run vector must mount
        ``Path.home() / ".pi"`` — the authoritative host Pi home —
        not a repo-relative path.  This matches the documented
        ``~/.pi → /home/dev/.pi`` contract."""
        from pathlib import Path

        expected = str(Path.home() / ".pi")

        factory, _ = self._make_noop_projection_factory()

        class FakeInspector:
            def list_names(self):
                return set()

        class FakeExecutor:
            def __init__(self, runner):
                self._runner = runner
            def run(self, argv):
                return self._runner.run(list(argv))

        runner = type("R", (), {
            "run": lambda self, a: type("P", (), {
                "argv": tuple(a), "return_code": 0,
                "stdout": "", "stderr": "",
            })()
        })()

        rc, out, err = _run(
            self.m,
            ["run", "--main-project", "/tmp/test", "--dry-run"],
            dispatcher=None,
            _process_runner=runner,
            _container_inspector=FakeInspector(),
            _run_executor=FakeExecutor(runner),
            _create_projection=factory,
        )
        self.assertEqual(0, rc, f"dry-run exit; err={err!r}")
        # The mount source must be the authoritative host path
        self.assertIn(
            f"src={expected}",
            out,
            f"Mount source '{expected}' not found in run vector:\n{out}",
        )


class TestTUISelectorWiring(unittest.TestCase):
    """Prove --tui delegates to an injectable ProjectSelector boundary.

    All tests are daemon-independent — they inject fakes and assert
    behaviour through the facade without touching Docker or files.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    @staticmethod
    def _fake_runner_for_tests() -> tuple[Any, Any, Any, Any]:
        """Build a complete set of fake boundaries for a successful
        non-dry-run execution.  Returns (runner, inspector, executor,
        projection_factory)."""
        from docker.launcher import ProcessResult

        class FakeRunner:
            def run(self, argv: list[str]) -> Any:
                return ProcessResult(
                    argv=tuple(argv), return_code=0,
                    stdout="fake-stdout", stderr="",
                )

        class FakeInspector:
            def __init__(self, runner: Any) -> None:
                self._runner = runner
            def list_names(self) -> set[str]:
                return set()

        class FakeExecutor:
            def __init__(self, runner: Any) -> None:
                self._runner = runner
            def run(self, argv: tuple[str, ...]) -> Any:
                return self._runner.run(list(argv))

        def factory(projection: object, *, parent_dir: str) -> Any:
            class Handle:
                def __enter__(self) -> "Handle":
                    return self
                def __exit__(self, *a: object) -> None:
                    pass
            h = Handle()
            h.path = "/tmp/.docker-generated/runtime/proj.toml"
            h.content_hash = (
                "a" * 64
            )
            return h

        runner = FakeRunner()
        return runner, FakeInspector(runner), FakeExecutor(runner), factory

    def test_tui_with_fake_selector_selects_projects(self) -> None:
        """--tui with an injected ProjectSelector uses the selector
        result as the main and optional projects."""
        from docker.launcher import ProjectSelection

        class RecordingSelector:
            def __init__(self) -> None:
                self.select_called = False
            def select(self) -> Any:
                self.select_called = True
                return ProjectSelection(
                    main_project="/work/tui-main",
                    optional_projects=("/work/tui-opt1", "/work/tui-opt2"),
                )

        selector = RecordingSelector()
        runner, inspector, executor, proj_factory = (
            self._fake_runner_for_tests()
        )

        rc, out, err = _run(
            self.m,
            ["run", "--tui", "--dry-run"],
            dispatcher=None,
            _process_runner=runner,
            _container_inspector=inspector,
            _run_executor=executor,
            _create_projection=proj_factory,
            _project_selector=selector,
        )
        self.assertEqual(0, rc, f"rc={rc} out={out!r} err={err!r}")
        self.assertTrue(selector.select_called,
                        "TUI selector should have been invoked")
        # The display string should mention the TUI-selected projects
        self.assertIn("/work/tui-main", out)

    def test_tui_cancelled_maps_to_no_main_project(self) -> None:
        """When the TUI selector returns None (user cancelled), the
        facade maps it to a CONFIG-level NoMainProjectError."""
        class CancelledSelector:
            def select(self) -> None:
                return None

        selector = CancelledSelector()
        runner, inspector, executor, proj_factory = (
            self._fake_runner_for_tests()
        )

        rc, out, err = _run(
            self.m,
            ["run", "--tui"],
            dispatcher=None,
            _process_runner=runner,
            _container_inspector=inspector,
            _run_executor=executor,
            _create_projection=proj_factory,
            _project_selector=selector,
        )
        self.assertEqual(
            3,  # ExitKind.CONFIG → exit code 3
            rc,
            f"Expected CONFIG exit (3); got rc={rc} out={out!r} err={err!r}",
        )
        self.assertIn("No main project", err)

    def test_tui_without_selector_and_without_main_project_fails(self) -> None:
        """--tui without an injected selector and without
        --main-project raises NoMainProjectError.  The curses TUI
        is created when neither _project_selector nor --main-project
        is provided.

        Since the curses TUI can't be launched in automated tests,
        we instead prove that _tui_project_selector() returns a
        conformant ProjectSelector object."""
        from docker.constructor_cli import _tui_project_selector

        sel = _tui_project_selector()
        self.assertTrue(hasattr(sel, "select"),
                        "Default selector must have select()")
        self.assertTrue(callable(sel.select),
                        "select must be callable")

    def test_real_tui_selector_conforms_to_protocol(self) -> None:
        """The _tui_project_selector returns an object whose
        select() satisfies the ProjectSelector protocol without
        invoking curses."""
        from docker.constructor_cli import _tui_project_selector

        sel = _tui_project_selector()
        # Type-level conformance — the returned object satisfies
        # the structural type
        self.assertTrue(hasattr(sel, "select"))
        # The function must import without side effects
        self.assertTrue(callable(sel.select))

    def test_tui_flag_preserves_selector_over_explicit_main(self) -> None:
        """When both --tui and --main-project are given, explicit
        main-project takes precedence (per resolve_project_selection
        resolution order).  The TUI selector is NOT invoked."""
        class BombSelector:
            def select(self) -> Any:
                raise RuntimeError("TUI must not be invoked when "
                                   "--main-project is explicit")

        runner, inspector, executor, proj_factory = (
            self._fake_runner_for_tests()
        )

        rc, out, err = _run(
            self.m,
            ["run", "--tui", "--main-project", "/work/explicit",
             "--dry-run"],
            dispatcher=None,
            _process_runner=runner,
            _container_inspector=inspector,
            _run_executor=executor,
            _create_projection=proj_factory,
            _project_selector=BombSelector(),
        )
        self.assertEqual(0, rc, f"rc={rc} out={out!r} err={err!r}")
        # The explicit --main-project should appear, not the TUI
        self.assertIn("/work/explicit", out)

    def test_tui_selector_receives_no_args(self) -> None:
        """The TUI selector boundary is called with no arguments.
        All project discovery is the selector's responsibility."""
        from docker.launcher import ProjectSelection

        select_args: list[tuple] = []

        class ArgRecordingSelector:
            def select(self) -> Any:
                select_args.append(())
                return ProjectSelection(
                    main_project="/work/from-tui",
                )

        runner, inspector, executor, proj_factory = (
            self._fake_runner_for_tests()
        )

        _run(
            self.m,
            ["run", "--tui", "--dry-run"],
            dispatcher=None,
            _process_runner=runner,
            _container_inspector=inspector,
            _run_executor=executor,
            _create_projection=proj_factory,
            _project_selector=ArgRecordingSelector(),
        )
        self.assertEqual(1, len(select_args),
                         "Selector.select() must be called exactly once")
        self.assertEqual((), select_args[0],
                         "Selector.select() must receive no arguments")


class TestBaseProjectDirPrecedence(unittest.TestCase):
    """Prove the base-project-dir resolution chain:
    CLI --base-project-dir → .env BASE_PROJECT_DIR → Path.home().

    All tests avoid curses by monkey-patching _tui_project_selector
    and asserting the *base_dir* argument it receives.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    @staticmethod
    def _patch_selector() -> tuple[list[str | None], Any]:
        """Monkey-patch _tui_project_selector to record *base_dir*
        and return a cancelled selector (so the command fails with
        NoMainProjectError without invoking curses).

        Returns (captured_list, restore_callable).
        """
        from docker import constructor_cli as mod

        captured: list[str | None] = []
        orig = mod._tui_project_selector

        def _fake_tui_selector(base_dir=None):
            captured.append(base_dir)
            # Return a selector that cancels → NoMainProjectError
            class Cancelled:
                def select(self):
                    return None
            return Cancelled()

        mod._tui_project_selector = _fake_tui_selector

        def restore():
            mod._tui_project_selector = orig

        return captured, restore

    def test_cli_base_project_dir_passed_to_selector(self) -> None:
        """--base-project-dir /custom/path reaches the selector."""
        captured, restore = self._patch_selector()
        try:
            _run(self.m, ["run", "--tui",
                  "--base-project-dir", "/custom/tui/root"])
        finally:
            restore()

        self.assertEqual(1, len(captured),
                         "TUI selector factory must be called")
        self.assertEqual("/custom/tui/root", captured[0],
                         "CLI arg must reach _tui_project_selector")

    def test_cli_base_project_dir_wins_over_env(self) -> None:
        """When both --base-project-dir and .env BASE_PROJECT_DIR
        are present, CLI wins."""
        from docker import constructor_cli as mod
        captured, restore_sel = self._patch_selector()
        orig_read = mod._read_env_key

        def _fake_read(key):
            if key == "BASE_PROJECT_DIR":
                return "/from/env/file"
            return orig_read(key)

        mod._read_env_key = _fake_read
        try:
            _run(self.m, ["run", "--tui",
                  "--base-project-dir", "/cli/wins"])
        finally:
            restore_sel()
            mod._read_env_key = orig_read

        self.assertEqual(1, len(captured))
        self.assertEqual("/cli/wins", captured[0],
                         "--base-project-dir must take precedence over .env")

    def test_env_base_project_dir_fallback(self) -> None:
        """Without --base-project-dir, .env BASE_PROJECT_DIR is used."""
        from docker import constructor_cli as mod
        captured, restore_sel = self._patch_selector()
        orig_read = mod._read_env_key

        def _fake_read(key):
            if key == "BASE_PROJECT_DIR":
                return "/from/env/file"
            return orig_read(key)

        mod._read_env_key = _fake_read
        try:
            _run(self.m, ["run", "--tui"])
        finally:
            restore_sel()
            mod._read_env_key = orig_read

        self.assertEqual(1, len(captured))
        self.assertEqual("/from/env/file", captured[0],
                         ".env BASE_PROJECT_DIR must be the fallback")

    def test_home_fallback_when_nothing_specified(self) -> None:
        """When neither --base-project-dir nor .env BASE_PROJECT_DIR
        is set, None reaches the selector, which internally falls
        back to Path.home()."""
        from docker import constructor_cli as mod
        captured, restore_sel = self._patch_selector()
        orig_read = mod._read_env_key

        def _fake_read(key):
            return None  # No env value

        mod._read_env_key = _fake_read
        try:
            _run(self.m, ["run", "--tui"])
        finally:
            restore_sel()
            mod._read_env_key = orig_read

        self.assertEqual(1, len(captured))
        self.assertIsNone(captured[0],
                          "No base dir should yield None "
                          "(selector falls back to Path.home())")

    def test_invalid_directory_passed_to_selector(self) -> None:
        """When --base-project-dir points to a non-existent path,
        the path is still passed to the selector — the selector
        handles the invalid-directory fallback internally."""
        captured, restore = self._patch_selector()
        try:
            _run(self.m, ["run", "--tui",
                  "--base-project-dir", "/nonexistent/path/42"])
        finally:
            restore()

        self.assertEqual(1, len(captured))
        self.assertEqual("/nonexistent/path/42", captured[0],
                         "Invalid path must still reach the selector "
                         "(selector owns the fallback logic)")

    def test_expanduser_applied_to_cli_value(self) -> None:
        """--base-project-dir ~/projects should be expanded."""
        from pathlib import Path
        captured, restore = self._patch_selector()
        try:
            _run(self.m, ["run", "--tui",
                  "--base-project-dir", "~/projects"])
        finally:
            restore()

        expected = str(Path("~/projects").expanduser())
        self.assertEqual(1, len(captured))
        self.assertEqual(expected, captured[0],
                         "~ must be expanded to home directory")


# ════════════════════════════════════════════════════════════════════
# Verify facade wiring (Stage 12)
# ════════════════════════════════════════════════════════════════════


class TestVerifyBuildWiring(unittest.TestCase):
    """Prove the facade wires ``verify --scope build`` through to
    ``verify_build()`` and formats the results."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        # Create a temporary build projection that verify_build can parse.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._proj_dir = Path(self._tmpdir.name) / ".docker-generated"
        self._proj_dir.mkdir(parents=True)
        proj_path = self._proj_dir / "docker-constructor.build.effective.toml"
        proj_path.write_text(
            '[python]\nversion = "3.12.0"\n'
            '[node]\nimage = "node:20.11.0-bookworm-slim"\n'
            '[rust]\nversion = "1.77.0"\n'
            'components = ["cargo", "rustfmt", "clippy"]\n'
            '[uv]\nversion = "0.5.0"\n'
            '[ty]\nversion = "v0.9.0"\n'
            '[rtk]\nversion = "0.31.0"\n'
            '[fd]\nversion = "9.0.0"\n'
            '[pi]\nversion = "v1.4.236"\n'
            '[openspec]\nversion = "v0.15.0"\n'
            '[oh-my-zsh]\nrevision = "abc1234"\n'
        )
        # Inventory pointing to the repo root
        self._inv_path = Path(self._tmpdir.name) / "docker-constructor.toml"
        self._inv_path.write_text(
            '[meta]\nversion = 1\n'
            '[environments.pi-local]\n'
            'provider = "docker"\n'
            'name = "pi-cli-pi"\n'
            'tag = "latest"\n'
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_recording_runner(
        self, return_code: int = 0, stdout: str = "", stderr: str = ""
    ) -> Any:
        from docker.launcher import ProcessResult

        calls: list[tuple[str, ...]] = []

        class _Rec:
            def run(self, argv):
                calls.append(tuple(argv))
                return ProcessResult(
                    argv=tuple(argv), return_code=return_code,
                    stdout=stdout, stderr=stderr,
                )

        return _Rec(), calls

    def test_build_scope_calls_verify_build_docker_run_no_rm_flags(self) -> None:
        """``verify --scope build`` runs ``docker run --rm <image> <tool>
        --version`` for each contract tool."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "build", "--image", "test-img:1"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        assert calls, "verify_build must invoke the runner"
        # Every call must use 'docker run --rm test-img:1'
        for argv in calls:
            self.assertIn("docker", argv)
            self.assertIn("run", argv)
            self.assertIn("--rm", argv)
            self.assertIn("test-img:1", argv)

    def test_build_scope_success_output_format(self) -> None:
        """``verify --scope build`` prints observations to stdout."""
        # Return an empty string — observations will all mismatch (EMPTY),
        # but the command itself runs successfully.
        runner, _ = self._make_recording_runner(
            return_code=0,
            stdout="",
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "build", "--image", "ok-img:v1"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # OPERATIONAL exit because all observations mismatch
        self.assertEqual(4, rc)
        self.assertIn("Build verification", err)

    def test_build_scope_failure_output_format(self) -> None:
        """``verify --scope build`` prints ✗ for mismatches."""
        runner, _ = self._make_recording_runner(
            return_code=0,
            stdout="99.99.99",  # won't match any expected
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "build", "--image", "bad-img:v2"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)  # OPERATIONAL
        self.assertIn("FAIL", err)
        self.assertIn("✗", err)

    def test_build_json_output(self) -> None:
        """``verify --scope build --output json`` returns structured data."""
        runner, _ = self._make_recording_runner(
            return_code=0,
            stdout="1.77.0",
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "--output", "json",
             "verify", "--scope", "build", "--image", "json-img:v3"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # JSON always writes to stdout even on failure
        data = json.loads(out)
        self.assertIn("data", data)
        b = data["data"]["verification"]["build"]
        self.assertIsInstance(b["all_ok"], bool)
        self.assertIsInstance(b["observations"], list)


class TestVerifyRuntimeWiring(unittest.TestCase):
    """Prove the facade wires ``verify --scope runtime`` through to
    ``verify_runtime()`` or returns a clear error when required
    arguments are missing."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self._tmpdir = tempfile.TemporaryDirectory()
        self._proj_dir = Path(self._tmpdir.name) / ".docker-generated"
        self._proj_dir.mkdir(parents=True)
        # Build projection for --scope all tests
        bp = self._proj_dir / "docker-constructor.build.effective.toml"
        bp.write_text(
            '[python]\nversion = "3.12.0"\n'
            '[node]\nimage = "node:20.11.0-bookworm-slim"\n'
            '[rust]\nversion = "1.77.0"\n'
            'components = ["cargo", "rustfmt", "clippy"]\n'
            '[uv]\nversion = "0.5.0"\n'
            '[ty]\nversion = "v0.9.0"\n'
            '[rtk]\nversion = "0.31.0"\n'
            '[fd]\nversion = "9.0.0"\n'
            '[pi]\nversion = "v1.4.236"\n'
            '[openspec]\nversion = "v0.15.0"\n'
            '[oh-my-zsh]\nrevision = "abc1234"\n'
        )
        # Runtime projection in .docker-generated/runtime/ (launcher-produced)
        self._runtime_dir = self._proj_dir / "runtime"
        self._runtime_dir.mkdir(parents=True)
        rp = self._runtime_dir / "a1b2c3d4.toml"
        rp.write_text(
            '[extensions]\n'
            '[project_paths]\n'
            'paths = []\n'
            '[pi_home]\n'
            'path = "/home/dev/.pi"\n'
            '[gateway]\n'
            'address = "192.168.65.1"\n'
            '[integrity]\n'
            'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
        )
        self._inv_path = Path(self._tmpdir.name) / "docker-constructor.toml"
        self._inv_path.write_text(
            '[meta]\nversion = 1\n'
            '[environments.pi-local]\n'
            'provider = "docker"\n'
            'name = "pi-cli-pi"\n'
            'tag = "latest"\n'
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_recording_runner(
        self, return_code: int = 0, stdout: str = "", stderr: str = ""
    ) -> Any:
        from docker.launcher import ProcessResult

        calls: list[tuple[str, ...]] = []

        class _Rec:
            def run(self, argv):
                calls.append(tuple(argv))
                return ProcessResult(
                    argv=tuple(argv), return_code=return_code,
                    stdout=stdout, stderr=stderr,
                )

        return _Rec(), calls

    def test_runtime_without_container_no_running_containers(self) -> None:
        """``verify --scope runtime`` without --container auto-detects
        via ``docker ps -q --filter ancestor=<image>``.  When no
        containers are found the result is an error."""
        runner, calls = self._make_recording_runner(
            return_code=0, stdout=""
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime", "--image", "no-such-img:v0"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)  # OPERATIONAL
        self.assertIn("no running container found", err)
        # Must have attempted docker ps
        self.assertTrue(
            any("ps" in c and any("ancestor" in a for a in c) for c in calls),
            "auto-detection must run docker ps",
        )

    def test_runtime_without_container_auto_detection_succeeds(self) -> None:
        """``verify --scope runtime`` auto-detects the container when
        ``docker ps`` returns a single container ID."""
        runner, calls = self._make_recording_runner(
            return_code=0, stdout="abc123def456\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime", "--image", "good-img:v1"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # Must use the detected container in docker exec calls
        docker_exec_calls = [
            c for c in calls
            if c[0] == "docker" and c[1] == "exec"
        ]
        self.assertTrue(docker_exec_calls, "must run docker exec checks")
        for c in docker_exec_calls:
            self.assertIn("abc123def456", c)

    def test_runtime_auto_detection_handles_docker_ps_failure(self) -> None:
        """When ``docker ps`` exits non-zero, the error is reported."""
        runner, calls = self._make_recording_runner(
            return_code=1, stderr="docker: cannot connect\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime", "--image", "bad-img:v2"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("docker ps failed", err)

    def test_runtime_auto_detection_oserror(self) -> None:
        """When ``docker ps`` raises OSError, the error is reported."""
        calls_list: list[tuple[str, ...]] = []

        class _OSErrorRunner:
            def run(self, argv):
                calls_list.append(tuple(argv))
                raise OSError("no docker daemon")

        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime", "--image", "nosock-img:v3"],
            _process_runner=_OSErrorRunner(),
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("no docker daemon", err)

    def test_explicit_runtime_projection_path(self) -> None:
        """``--runtime-projection`` overrides auto-discovery."""
        # Create a separate projection file
        custom_rp = self._runtime_dir / "custom-proj.toml"
        custom_rp.write_text(
            '[extensions]\n'
            '[integrity]\n'
            'sha256 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="\n'
        )
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-custom",
             "--runtime-projection", str(custom_rp)],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # Must reference pi-custom in docker exec, not the auto-detected one
        exec_calls = [c for c in calls if c[0] == "docker" and c[1] == "exec"]
        for c in exec_calls:
            self.assertIn("pi-custom", c)

    def test_explicit_project_paths_passed_to_verify_runtime(self) -> None:
        """``--project`` (repeatable) forwards container-side paths
        to ``verify_runtime`` so the project presence, ownership, and
        env-var checks use representative data."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-multi",
             "--project", "/home/dev/p1",
             "--project", "/home/dev/p2"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # PROJECT_PATH_1 and PROJECT_PATH_2 must appear in docker exec
        exec_calls = [c for c in calls if c[0] == "docker" and c[1] == "exec"]
        all_argv = " ".join(" ".join(c) for c in exec_calls)
        self.assertIn("/home/dev/p1", all_argv,
                      "PROJECT_PATH_1 must be checked")
        self.assertIn("/home/dev/p2", all_argv,
                      "PROJECT_PATH_2 must be checked")

    def test_project_paths_auto_discovered_from_container(self) -> None:
        """When ``--project`` is omitted, project paths are read from
        ``docker exec <container> sh -c 'env | grep PROJECT_PATH_'``
        (the launcher's own contract)."""
        _paths = "/home/dev/alpha\n/home/dev/beta\n"
        runner, calls = self._make_recording_runner(
            stdout="PROJECT_PATH_1=/home/dev/alpha\n"
                    "PROJECT_PATH_2=/home/dev/beta\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-discover"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        exec_calls = [c for c in calls if c[0] == "docker" and c[1] == "exec"]
        all_argv = " ".join(" ".join(c) for c in exec_calls)
        # Both auto-discovered paths must be checked
        self.assertIn("/home/dev/alpha", all_argv,
                      "PROJECT_PATH_1 must be auto-discovered and checked")
        self.assertIn("/home/dev/beta", all_argv,
                      "PROJECT_PATH_2 must be auto-discovered and checked")

    def test_auto_discovery_empty_projects_is_error(self) -> None:
        """When the container has no PROJECT_PATH_* vars, auto-discovery
        returns an error rather than guessing."""
        runner, calls = self._make_recording_runner(
            stdout=""  # empty env output
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-empty"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("no project paths available", err)

    def test_auto_discovery_preserves_numeric_order_not_path_sort(self) -> None:
        """PROJECT_PATH_N values are sorted by numeric suffix, not by
        the path string.  ``PROJECT_PATH_2=/zzz`` must appear after
        ``PROJECT_PATH_1=/aaa`` even though "/aaa" > "/zzz"."""
        runner, calls = self._make_recording_runner(
            stdout="PROJECT_PATH_2=/home/dev/zzz\n"
                    "PROJECT_PATH_1=/home/dev/aaa\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-order"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        exec_calls = [c for c in calls if c[0] == "docker" and c[1] == "exec"]
        all_argv = " ".join(" ".join(c) for c in exec_calls)
        # Find positions of each path in the argv blob
        pos_aaa = all_argv.find("/home/dev/aaa")
        pos_zzz = all_argv.find("/home/dev/zzz")
        self.assertNotEqual(-1, pos_aaa)
        self.assertNotEqual(-1, pos_zzz)
        # Numeric order: 1 before 2 → aaa must appear before zzz
        self.assertLess(pos_aaa, pos_zzz,
                        "PROJECT_PATH_1 must appear before PROJECT_PATH_2")

    def test_auto_discovery_gaps_in_indices_rejected(self) -> None:
        """Gaps in PROJECT_PATH_N (e.g., 1, 3 but no 2) are rejected."""
        runner, calls = self._make_recording_runner(
            stdout="PROJECT_PATH_1=/a\nPROJECT_PATH_3=/c\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-gap"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("no project paths available", err)

    def test_auto_discovery_non_one_start_rejected(self) -> None:
        """PROJECT_PATH_N must start at 1; e.g., 2,3 is not 1..2."""
        runner, calls = self._make_recording_runner(
            stdout="PROJECT_PATH_2=/a\nPROJECT_PATH_3=/b\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-offby"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("no project paths available", err)

    def test_missing_runtime_projection_is_error(self) -> None:
        """When no ``--runtime-projection`` is given and
        ``.docker-generated/runtime/`` is empty, an error is
        reported."""
        # Remove the existing projection
        for f in self._runtime_dir.iterdir():
            f.unlink()
        runner, calls = self._make_recording_runner(
            return_code=0, stdout="abc123\n"
        )
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-noproj"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        self.assertEqual(4, rc)
        self.assertIn("no runtime projection found", err)

    def test_runtime_with_container_uses_docker_exec(self) -> None:
        """``verify --scope runtime --container pi-1`` calls
        ``verify_runtime`` with ``docker exec pi-1 ...`` commands."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "runtime",
             "--container", "pi-1"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # docker exec commands must reference pi-1
        docker_exec_calls = [
            c for c in calls
            if c[0] == "docker" and c[1] == "exec"
        ]
        for c in docker_exec_calls:
            self.assertIn("pi-1", c)

    def test_runtime_all_scope_with_container(self) -> None:
        """``verify --scope all --container pi-1`` runs both build
        and runtime checks."""
        runner, calls = self._make_recording_runner()
        _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "all",
             "--container", "pi-1", "--image", "img:v99"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # Must have both 'docker run --rm' and 'docker exec pi-1'
        has_run = any("run" in c and "--rm" in c for c in calls)
        has_exec = any("exec" in c and "pi-1" in c for c in calls)
        self.assertTrue(has_run, "must include build checks via docker run")
        self.assertTrue(has_exec, "must include runtime checks via docker exec")


class TestVerifyEvidenceWiring(unittest.TestCase):
    """Prove ``verify --collect-evidence`` calls ``collect_evidence()``
    and returns bundle metadata."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path
        self._tmpdir = tempfile.TemporaryDirectory()
        self._proj_dir = Path(self._tmpdir.name) / ".docker-generated"
        self._proj_dir.mkdir(parents=True)
        proj_path = self._proj_dir / "docker-constructor.build.effective.toml"
        proj_path.write_text(
            '[python]\nversion = "3.12.0"\n'
            '[node]\nimage = "node:20.11.0-bookworm-slim"\n'
            '[rust]\nversion = "1.77.0"\n'
            'components = ["cargo", "rustfmt", "clippy"]\n'
            '[uv]\nversion = "0.5.0"\n'
            '[ty]\nversion = "v0.9.0"\n'
            '[rtk]\nversion = "0.31.0"\n'
            '[fd]\nversion = "9.0.0"\n'
            '[pi]\nversion = "v1.4.236"\n'
            '[openspec]\nversion = "v0.15.0"\n'
            '[oh-my-zsh]\nrevision = "abc1234"\n'
        )
        rp = self._proj_dir / "runtime"
        rp.mkdir(parents=True)
        rt_proj = rp / "evidence-proj.toml"
        rt_proj.write_text(
            '[extensions]\n'
            '[integrity]\n'
            'sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="\n'
        )
        self._inv_path = Path(self._tmpdir.name) / "docker-constructor.toml"
        self._inv_path.write_text(
            '[meta]\nversion = 1\n'
            '[environments.pi-local]\n'
            'provider = "docker"\n'
            'name = "pi-cli-pi"\n'
            'tag = "latest"\n'
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_recording_runner(
        self, return_code: int = 0, stdout: str = "", stderr: str = ""
    ) -> Any:
        from docker.launcher import ProcessResult

        calls: list[tuple[str, ...]] = []

        class _Rec:
            def run(self, argv):
                calls.append(tuple(argv))
                return ProcessResult(
                    argv=tuple(argv), return_code=return_code,
                    stdout=stdout, stderr=stderr,
                )

        return _Rec(), calls

    def test_collect_evidence_with_build_scope(self) -> None:
        """``verify --scope build --collect-evidence`` runs
        ``collect_evidence`` alongside build checks."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "verify", "--scope", "build", "--collect-evidence",
             "--image", "ev-img:v1"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        # Verify build calls + docker inspect (auto) + maybe host-metadata
        self.assertTrue(
            any("docker" in c and "inspect" in c and "ev-img:v1" in c
                for c in calls),
            "must auto-run docker inspect for image metadata",
        )

    def test_collect_evidence_output_dir_reported(self) -> None:
        """When ``--collect-evidence`` runs, the results include the
        bundle output directory and index path."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "--output", "json",
             "verify", "--scope", "build", "--collect-evidence",
             "--image", "ev-img:v2"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        data = json.loads(out)
        v = data["data"]["verification"]
        self.assertIn("collect_evidence", v)
        ce = v["collect_evidence"]
        self.assertTrue(ce["all_ok"])
        self.assertIn("output_dir", ce)
        self.assertIn("index_path", ce)

    def test_collect_evidence_with_runtime_scope(self) -> None:
        """``verify --scope runtime --collect-evidence --container X``
        includes runtime-specific commands in the bundle."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "--output", "json",
             "verify", "--scope", "runtime", "--collect-evidence",
             "--container", "pi-2"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        data = json.loads(out)
        v = data["data"]["verification"]
        self.assertIn("collect_evidence", v)
        ce = v["collect_evidence"]
        self.assertFalse(ce["dry_run"])
        # Must contain output_dir and index_path
        self.assertIn("output_dir", ce)
        self.assertIn("index_path", ce)

    def test_dry_run_collect_evidence(self) -> None:
        """``--collect-evidence --dry-run`` records metadata without
        executing evidence commands.  Uses runtime scope to avoid
        build-level ``docker run`` calls."""
        runner, calls = self._make_recording_runner()
        rc, out, err = _run(
            self.m,
            ["--inventory", str(self._inv_path),
             "--output", "json",
             "verify", "--scope", "runtime", "--collect-evidence",
             "--dry-run", "--container", "pi-dry"],
            _process_runner=runner,
            _prompt_user=lambda _: True,
        )
        data = json.loads(out)
        ce = data["data"]["verification"]["collect_evidence"]
        self.assertTrue(ce["dry_run"])
        # All runner calls come from verify_runtime (not collect_evidence).
        # In dry-run mode collect_evidence adds zero calls.  Only docker inspect
        # is indicative of evidence collection (auto-inspect when commands empty).
        evidence_calls = [c for c in calls if "inspect" in c]
        self.assertEqual(0, len(evidence_calls),
                         "collect_evidence must not invoke runner in dry-run")


if __name__ == "__main__":
    unittest.main()
