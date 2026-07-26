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


if __name__ == "__main__":
    unittest.main()
