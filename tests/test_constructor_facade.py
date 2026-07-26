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
from typing import Any, Sequence

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
) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main(
            list(argv),
            dispatcher=dispatcher,
            stdout_isatty=lambda: stdout_isatty,
            stderr_isatty=lambda: stderr_isatty,
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


if __name__ == "__main__":
    unittest.main()
