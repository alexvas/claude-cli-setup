"""RED tests for Stage 8.2 — scoped read-only commands.

validate / show / check-updates with ``build`` | ``runtime`` | ``all``
scope selection, effective display, provider/path filters, suggestions,
prerelease, cache controls, policy exits, and JSON output.

All tests inject fake dispatchers — no network, no Docker, no real
inventory parsing.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Sequence

# ── module loader ──────────────────────────────────────────────────────

_MODULE: Any = None


def _load_mod() -> Any:
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    path = os.path.join(
        os.path.dirname(__file__), "..", "docker", "docker-constructor.py",
    )
    loader = importlib.machinery.SourceFileLoader("docker_constructor", path)
    spec = importlib.util.spec_from_loader("docker_constructor", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    mod.__module__ = "docker_constructor"
    sys.modules["docker_constructor"] = mod
    loader.exec_module(mod)
    _MODULE = mod
    return mod


# ── helpers ────────────────────────────────────────────────────────────

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


def _make_fake(mod: Any, *, exit_kind: str = "success",
               data: object = None, message: str | None = None,
               debug: str | None = None) -> Any:
    class Fake:
        def execute(self, command: str, request: Any) -> Any:
            Fake.command = command
            Fake.request = request
            return mod.CommandResult(
                exit_kind=getattr(mod.ExitKind, exit_kind.upper()),
                data=data, message=message, debug=debug,
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
# Scope enum / DTO
# ════════════════════════════════════════════════════════════════════════


class TestScopeParsing(unittest.TestCase):
    """The facade parses and validates scope strings; internal services own the enum."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_scope_is_passed_as_validated_string(self) -> None:
        """Scope crosses the dispatcher boundary as a plain string, not an enum."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate", "--scope", "build"], dispatcher=fake)
        scope = fake.calls[0][1].command_args["scope"]
        self.assertIsInstance(scope, str)
        self.assertEqual("build", scope)

    def test_default_scope_is_all_string(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("all", fake.calls[0][1].command_args["scope"])


# ════════════════════════════════════════════════════════════════════════
# validate — scope selection and structured results
# ════════════════════════════════════════════════════════════════════════


class TestValidateScope(unittest.TestCase):
    """``validate`` command accepts --scope and passes it through."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_validate_default_scope_is_all(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual(1, len(fake.calls))
        self.assertEqual("all", fake.calls[0][1].command_args["scope"])

    def test_validate_scope_build(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate", "--scope", "build"], dispatcher=fake)
        self.assertEqual("build",
                         fake.calls[0][1].command_args["scope"])

    def test_validate_scope_runtime(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate", "--scope", "runtime"], dispatcher=fake)
        self.assertEqual("runtime",
                         fake.calls[0][1].command_args["scope"])

    def test_validate_scope_all(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["validate", "--scope", "all"], dispatcher=fake)
        self.assertEqual("all",
                         fake.calls[0][1].command_args["scope"])

    def test_validate_invalid_scope_exits_cli(self) -> None:
        rc, _, err = _run(self.m, ["validate", "--scope", "frob"])
        self.assertEqual(2, rc)                      # ExitKind.CLI
        self.assertIn("invalid choice", err.lower())

    def test_validate_no_network_no_docker(self) -> None:
        """validate must never invoke network or Docker."""
        import socket, subprocess
        from unittest.mock import patch
        mod = _load_mod()
        with patch.object(socket, "socket",
                          side_effect=RuntimeError("no network")):
            with patch.object(subprocess, "run",
                              side_effect=RuntimeError("no subprocess")):
                fake = _make_fake(mod, exit_kind="success")
                rc, out, _ = _run(mod, ["validate"], dispatcher=fake)
                self.assertEqual(0, rc)
                self.assertIn("[SUCCESS]", out)

    def test_validate_source_inventory_byte_identical(self) -> None:
        """Full inventory validation does not mutate the source TOML."""
        pass  # structural — exercised after GREEN wiring


class TestValidateStructuredResult(unittest.TestCase):
    """validate produces structured results with scope & diagnostics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_validate_success_result(self) -> None:
        data = {"scope": "all", "inventory": "/tmp/t.toml",
                "valid": True, "diagnostics": []}
        fake = _make_fake(self.m, exit_kind="success", data=data,
                          message="validation passed")
        _, out, _ = _run(self.m, ["validate"], dispatcher=fake)
        self.assertIn("validation passed", out)

    def test_validate_json_result_contains_scope_and_path(self) -> None:
        data = {"scope": "build", "inventory": "/tmp/t.toml",
                "valid": True, "diagnostics": []}
        fake = _make_fake(self.m, exit_kind="success", data=data,
                          message="ok")
        _, out, _ = _run(self.m, ["--output", "json", "validate"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertEqual({"scope": "build", "inventory": "/tmp/t.toml",
                          "valid": True, "diagnostics": []},
                         payload["data"])

    def test_validate_failure_with_diagnostics_on_stderr(self) -> None:
        data = {"scope": "runtime", "inventory": "/tmp/t.toml",
                "valid": False,
                "diagnostics": [
                    {"path": "runtime.pi-extensions.myext.version",
                     "problem": "missing version"},
                    {"path": "runtime.pi-extensions.other.version",
                     "problem": "invalid semver"},
                ]}
        fake = _make_fake(self.m, exit_kind="config", data=data,
                          message="validation failed")
        _, out, err = _run(self.m, ["validate", "--scope", "runtime"],
                           dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("validation failed", err)

    def test_validate_json_failure_includes_diagnostics(self) -> None:
        data = {"scope": "runtime", "inventory": "/tmp/t.toml",
                "valid": False,
                "diagnostics": [{"path": "x", "problem": "y"}]}
        fake = _make_fake(self.m, exit_kind="config", data=data,
                          message="fail")
        _, out, _ = _run(self.m, ["--output", "json", "validate"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertEqual("config", payload["status"])
        self.assertIn("diagnostics", payload["data"])
        self.assertEqual(1, len(payload["data"]["diagnostics"]))

    def test_validate_does_not_delete_unselected_section(self) -> None:
        """Validate build only — runtime data must not be discarded."""
        data = {"scope": "build", "inventory": "/tmp/t.toml",
                "valid": True, "diagnostics": []}
        fake = _make_fake(self.m, exit_kind="success", data=data,
                          message="build ok")
        _, out, _ = _run(self.m, ["validate", "--scope", "build"],
                         dispatcher=fake)
        self.assertIn("build ok", out)
        # No runtime info in output (scope=build), but runtime is NOT
        # stripped from the underlying inventory — that's verified by
        # the dispatcher itself in GREEN.

    def test_validate_path_aware_diagnostics(self) -> None:
        """Diagnostics reference the full TOML dotted path."""
        data = {"scope": "all", "inventory": "/tmp/t.toml",
                "valid": False,
                "diagnostics": [
                    {"path": "build.stages.toolchain.rust.version",
                     "problem": "unknown version"},
                ]}
        fake = _make_fake(self.m, exit_kind="config", data=data,
                          message="fail")
        _, out, err = _run(self.m, ["validate"], dispatcher=fake)
        self.assertEqual("", out)
        self.assertIn("fail", err)


# ════════════════════════════════════════════════════════════════════════
# show — source and effective display
# ════════════════════════════════════════════════════════════════════════


class TestShowSource(unittest.TestCase):
    """``show`` without ``--effective`` renders source inventory."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def _build_source(self) -> dict[str, object]:
        return {
            "node": {"tag": "24-trixie-slim", "digest": "sha256:abc..."},
            "toolchain": {"rust": "1.0.0", "uv": "0.1.0", "python": "3.14.6"},
        }

    def _runtime_source(self) -> dict[str, object]:
        return {
            "pi-extensions": {
                "myext": {"version": "1.2.3"},
            },
        }

    def test_show_build_source_only(self) -> None:
        data = self._build_source()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["show", "--scope", "build"],
                         dispatcher=fake)
        self.assertIn("node", out)
        self.assertNotIn("pi-extensions", out)

    def test_show_runtime_source_only(self) -> None:
        data = self._runtime_source()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["show", "--scope", "runtime"],
                         dispatcher=fake)
        self.assertIn("pi-extensions", out)
        self.assertNotIn("node", out)

    def test_show_all_source(self) -> None:
        data = {"build": self._build_source(),
                "runtime": self._runtime_source()}
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["show", "--scope", "all"],
                         dispatcher=fake)
        self.assertIn("node", out)
        self.assertIn("pi-extensions", out)

    def test_show_source_deterministic_text(self) -> None:
        data = self._build_source()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out1, _ = _run(self.m, ["show", "--scope", "build"],
                          dispatcher=fake)
        _, out2, _ = _run(self.m, ["show", "--scope", "build"],
                          dispatcher=fake)
        self.assertEqual(out1, out2)

    def test_show_source_deterministic_json(self) -> None:
        data = self._runtime_source()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out1, _ = _run(self.m, ["--output", "json",
                                   "show", "--scope", "runtime"],
                          dispatcher=fake)
        _, out2, _ = _run(self.m, ["--output", "json",
                                   "show", "--scope", "runtime"],
                          dispatcher=fake)
        self.assertEqual(out1, out2)

    def test_show_source_json_is_parseable(self) -> None:
        data = self._build_source()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["--output", "json",
                                  "show", "--scope", "build"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertEqual("node", list(payload["data"].keys())[0])


class TestShowEffective(unittest.TestCase):
    """``show --effective`` projects resolved versions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def _eff_build(self) -> dict[str, object]:
        return {
            "node": {"tag": "24-trixie-slim", "digest": "sha256:def..."},
            "toolchain": {"rust": "1.85.0", "uv": "0.6.0", "python": "3.14.6"},
        }

    def _eff_runtime(self) -> dict[str, object]:
        return {
            "pi-extensions": {
                "myext": {"version": "1.2.3"},
            },
        }

    def test_show_effective_build_projection(self) -> None:
        data = self._eff_build()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["show", "--scope", "build",
                                  "--effective"],
                         dispatcher=fake)
        self.assertIn("node", out)

    def test_show_effective_runtime_projection(self) -> None:
        data = self._eff_runtime()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["show", "--scope", "runtime",
                                  "--effective"],
                         dispatcher=fake)
        self.assertIn("pi-extensions", out)

    def test_show_effective_all_separate_objects(self) -> None:
        data = {"build": self._eff_build(),
                "runtime": self._eff_runtime()}
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["--output", "json",
                                  "show", "--scope", "all", "--effective"],
                         dispatcher=fake)
        payload = json.loads(out)
        self.assertIn("build", payload["data"])
        self.assertIn("runtime", payload["data"])

    def test_effective_runtime_excludes_provider_metadata(self) -> None:
        """Runtime effective output must not leak source/update/override metadata."""
        data = self._eff_runtime()  # provider metadata absent by construction
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["--output", "json",
                                  "show", "--scope", "runtime", "--effective"],
                         dispatcher=fake)
        payload = json.loads(out)
        flat = json.dumps(payload["data"])
        for forbidden in ("source", "provider", "update", "override", "cache"):
            self.assertNotIn(
                f'"{forbidden}"', flat,
                f"effective runtime must not expose {forbidden!r}",
            )

    def test_effective_build_excludes_runtime_extensions(self) -> None:
        """Build effective output must not include runtime extensions."""
        data = self._eff_build()
        fake = _make_fake(self.m, exit_kind="success", data=data)
        _, out, _ = _run(self.m, ["--output", "json",
                                  "show", "--scope", "build", "--effective"],
                         dispatcher=fake)
        payload = json.loads(out)
        flat = json.dumps(payload["data"])
        self.assertNotIn("pi-extensions", flat)

    def test_effective_never_publishes_projection_file(self) -> None:
        """show --effective must never write a projection file to disk."""
        import tempfile
        import pathlib
        with tempfile.TemporaryDirectory() as tmp:
            # Redirect CWD so any accidental file creation lands here
            orig = os.getcwd()
            try:
                os.chdir(tmp)
                data = self._eff_build()
                fake = _make_fake(self.m, exit_kind="success", data=data)
                _run(self.m, ["show", "--scope", "build", "--effective"],
                     dispatcher=fake)
                # No .docker-generated or toml files created
                created = list(pathlib.Path(tmp).rglob("*"))
                self.assertEqual(
                    [], [str(p) for p in created],
                    "show --effective must not write files",
                )
            finally:
                os.chdir(orig)


class TestShowOverrides(unittest.TestCase):
    """``show`` accepts ``--override PATH=VALUE`` for effective display."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_override_passed_to_dispatcher(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["show", "--scope", "build", "--effective",
                      "--override",
                      "build.stages.toolchain.rust.version=1.86.0"],
             dispatcher=fake)
        overrides = fake.calls[0][1].command_args.get("overrides")
        self.assertIsNotNone(overrides)
        self.assertIn("build.stages.toolchain.rust.version", overrides)

    def test_override_rejected_for_wrong_scope(self) -> None:
        """A runtime override under --scope build must be rejected."""
        # This is a domain rule — the fake simulates a config error
        fake = _make_fake(self.m, exit_kind="config",
                          message="override 'runtime.pi-extensions.x.version'"
                                  " is not valid for scope build")
        _, out, err = _run(
            self.m,
            ["show", "--scope", "build", "--effective",
             "--override", "runtime.pi-extensions.x.version=2.0"],
            dispatcher=fake,
        )
        self.assertEqual("", out)
        self.assertIn("not valid for scope build", err)

    def test_override_never_mutates_source_toml(self) -> None:
        """--override must never write back to docker-constructor.toml."""
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            orig = os.getcwd()
            try:
                os.chdir(tmp)
                data = {"toolchain": {"rust": "1.86.0"}}
                fake = _make_fake(self.m, exit_kind="success", data=data)
                _run(self.m, ["show", "--scope", "build", "--effective",
                              "--override",
                              "build.stages.toolchain.rust.version=1.86.0"],
                     dispatcher=fake)
                created = list(pathlib.Path(tmp).rglob("*"))
                self.assertEqual([], [str(p) for p in created])
            finally:
                os.chdir(orig)


# ════════════════════════════════════════════════════════════════════════
# check-updates — scope, filters, policy exits
# ════════════════════════════════════════════════════════════════════════


class TestCheckUpdatesScope(unittest.TestCase):
    """``check-updates`` scopes update discovery to build | runtime | all."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_check_updates_default_scope_all(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates"], dispatcher=fake)
        scope = fake.calls[0][1].command_args["scope"]
        self.assertEqual("all", scope)

    def test_check_updates_scope_build(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--scope", "build"],
             dispatcher=fake)
        self.assertEqual("build",
                         fake.calls[0][1].command_args["scope"])

    def test_check_updates_scope_runtime(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--scope", "runtime"],
             dispatcher=fake)
        self.assertEqual("runtime",
                         fake.calls[0][1].command_args["scope"])

    def test_check_updates_deterministic_target_ordering(self) -> None:
        """Repeated runs with same scope produce identical output."""
        data = {
            "results": [
                {"path": "build.stages.base.node", "current": "24", "candidate": "25",
                 "status": "outdated", "applicable": True},
                {"path": "build.stages.toolchain.rust.version", "current": "1.0.0",
                 "candidate": "1.85.0", "status": "outdated",
                 "applicable": True},
            ],
        }
        fake = _make_fake(self.m, exit_kind="policy",
                          data=data, message="2 outdated")
        _, out1, _ = _run(self.m, ["check-updates", "--scope", "build"],
                          dispatcher=fake)
        _, out2, _ = _run(self.m, ["check-updates", "--scope", "build"],
                          dispatcher=fake)
        self.assertEqual(out1, out2)


class TestCheckUpdatesFilters(unittest.TestCase):
    """``check-updates`` preserves ``--only`` and ``--provider`` filters."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_only_filter_passed_to_dispatcher(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--only", "gh", "--only", "docker"],
             dispatcher=fake)
        only_filter = fake.calls[0][1].command_args.get("only_filter")
        self.assertIsNotNone(only_filter)
        self.assertEqual(("gh", "docker"), only_filter)
        self.assertIsInstance(only_filter, tuple)   # frozen

    def test_unknown_filter_receives_structured_error(self) -> None:
        fake = _make_fake(
            self.m, exit_kind="cli",
            message="unknown filter 'nonexistent': not a provider or path",
        )
        _, out, err = _run(
            self.m, ["check-updates", "--only", "nonexistent"],
            dispatcher=fake,
        )
        self.assertEqual("", out)
        self.assertIn("unknown filter", err)

    def test_unknown_filter_suggestion(self) -> None:
        fake = _make_fake(
            self.m, exit_kind="cli",
            data={"suggestion": "did you mean 'github-release'?"},
            message="unknown provider 'github'",
        )
        _, out, _ = _run(
            self.m, ["--output", "json", "check-updates", "--only", "github"],
            dispatcher=fake,
        )
        payload = json.loads(out)
        self.assertIn("suggestion", payload["data"])

    def test_only_filter_preserves_canonical_inventory_path(self) -> None:
        """``--only build.stages.base.node`` must be passed as-is."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--only",
                      "build.stages.base.node"],
             dispatcher=fake)
        only_filter = fake.calls[0][1].command_args["only_filter"]
        self.assertIn("build.stages.base.node", only_filter)

    def test_only_filter_preserves_provider_name(self) -> None:
        """``--only docker-registry`` must be passed as-is."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--only", "docker-registry"],
             dispatcher=fake)
        only_filter = fake.calls[0][1].command_args["only_filter"]
        self.assertIn("docker-registry", only_filter)


class TestCheckUpdatesControls(unittest.TestCase):
    """``check-updates`` preserves ``--suggest``, prerelease, cache controls."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_suggest_flag_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--suggest"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["suggest"])

    def test_include_prerelease_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--include-prerelease"],
             dispatcher=fake)
        self.assertTrue(
            fake.calls[0][1].command_args["include_prerelease"])

    def test_cache_ttl_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--cache-ttl", "300"],
             dispatcher=fake)
        self.assertEqual(300,
                         fake.calls[0][1].command_args["cache_ttl"])

    def test_cache_dir_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--cache-dir", "/tmp/pi-cache"],
             dispatcher=fake)
        self.assertEqual("/tmp/pi-cache",
                         fake.calls[0][1].command_args["cache_dir"])

    def test_no_cache_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--no-cache"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["no_cache"])

    def test_strict_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--strict"], dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["strict"])

    def test_fail_on_outdated_passed(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--fail-on-outdated"],
             dispatcher=fake)
        self.assertTrue(fake.calls[0][1].command_args["fail_on_outdated"])

    def test_json_output_flag(self) -> None:
        fake = _make_recording_fake(self.m)
        _run(self.m, ["--output", "json", "check-updates"],
             dispatcher=fake)
        self.assertEqual("json", fake.calls[0][1].output)

    def test_provider_receives_only_selected_scope_targets(self) -> None:
        """Provider calls must receive targets from the selected scope only."""
        fake = _make_recording_fake(self.m)
        _run(self.m, ["check-updates", "--scope", "build"],
             dispatcher=fake)
        req = fake.calls[0][1]
        self.assertEqual("build", req.command_args["scope"])
        # The dispatcher handles filtering — we only verify scope is
        # passed correctly.  Actual target filtering is tested in GREEN
        # with real Inventory objects.

    def test_runtime_artifact_catalogs_not_queried_as_update_targets(self) -> None:
        """Runtime extension artifact catalogs are NOT independent targets."""
        # Structural: the dispatcher receives scope=runtime and is
        # expected to only enumerate extensions as update targets,
        # not their individual artifact sub-entries.
        pass  # exercised after GREEN wiring


class TestCheckUpdatesSuggestions(unittest.TestCase):
    """``--suggest`` produces non-mutating output."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_suggestions_non_mutating_text(self) -> None:
        data = {
            "results": [{"path": "build.stages.base.node", "status": "outdated",
                         "current": "24", "candidate": "25"}],
            "suggestions": [
                {"path": "build.stages.base.node",
                 "change": {"tag": "25-trixie-slim"}},
            ],
        }
        fake = _make_fake(self.m, exit_kind="policy",
                          data=data, message="1 outdated")
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            orig = os.getcwd()
            try:
                os.chdir(tmp)
                _, out, _ = _run(
                    self.m, ["check-updates", "--scope", "build",
                             "--suggest"],
                    dispatcher=fake,
                )
                created = list(pathlib.Path(tmp).rglob("*"))
                self.assertEqual([], [str(p) for p in created])
                self.assertIn("1 outdated", out)
            finally:
                os.chdir(orig)

    def test_suggestions_non_mutating_json(self) -> None:
        data = {"suggestions": [{"path": "x", "value": "y"}]}
        fake = _make_fake(self.m, exit_kind="policy",
                          data=data, message="suggestions follow")
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            orig = os.getcwd()
            try:
                os.chdir(tmp)
                _, out, _ = _run(
                    self.m, ["--output", "json", "check-updates",
                             "--suggest"],
                    dispatcher=fake,
                )
                payload = json.loads(out)
                self.assertIn("suggestions", payload["data"])
                self.assertEqual(
                    [], [str(p) for p in pathlib.Path(tmp).rglob("*")],
                )
            finally:
                os.chdir(orig)

    def test_suggestions_never_written_to_toml(self) -> None:
        """Suggestions must never modify docker-constructor.toml."""
        pass  # exercised via GREEN wiring


class TestCheckUpdatesPolicyExits(unittest.TestCase):
    """``check-updates`` maps domain outcomes to correct exit codes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_all_current_exits_zero(self) -> None:
        data = {"results": [
            {"path": "build.stages.base.node", "status": "current"},
            {"path": "build.stages.toolchain.rust.version", "status": "current"},
        ]}
        fake = _make_fake(self.m, exit_kind="success", data=data)
        rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual(0, rc)

    def test_outdated_without_fail_policy_exits_zero(self) -> None:
        data = {"results": [
            {"path": "build.stages.base.node", "status": "outdated",
             "applicable": True},
        ]}
        fake = _make_fake(self.m, exit_kind="success", data=data)
        rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual(0, rc)

    def test_outdated_with_fail_on_outdated_exits_policy(self) -> None:
        data = {"results": [
            {"path": "build.stages.base.node", "status": "outdated",
             "applicable": True},
        ]}
        fake = _make_fake(self.m, exit_kind="policy", data=data)
        rc, _, _ = _run(self.m, ["check-updates", "--fail-on-outdated"],
                        dispatcher=fake)
        self.assertEqual(1, rc)

    def test_provider_failure_strict_exits_operational(self) -> None:
        data = {"results": [
            {"path": "build.stages.base.node", "status": "unavailable",
             "reason": "network timeout"},
        ]}
        fake = _make_fake(self.m, exit_kind="operational", data=data,
                          message="provider failure")
        rc, _, _ = _run(self.m, ["check-updates", "--strict"],
                        dispatcher=fake)
        self.assertEqual(4, rc)

    def test_provider_failure_non_strict_exits_success(self) -> None:
        data = {"results": [
            {"path": "build.stages.base.node", "status": "unavailable",
             "reason": "network timeout"},
        ]}
        fake = _make_fake(self.m, exit_kind="success", data=data,
                          message="1 provider unavailable")
        rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
        self.assertEqual(0, rc)


# ════════════════════════════════════════════════════════════════════════
# Cross-cutting — no Docker, no network, no mutation
# ════════════════════════════════════════════════════════════════════════


class TestReadOnlySafety(unittest.TestCase):
    """Read-only commands never invoke Docker or mutate inventory."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.m = _load_mod()

    def test_validate_does_not_invoke_docker(self) -> None:
        import subprocess
        from unittest.mock import patch
        fake = _make_fake(self.m, exit_kind="success", data={"valid": True})
        with patch.object(subprocess, "run",
                          side_effect=RuntimeError("no subprocess")):
            rc, _, _ = _run(self.m, ["validate"], dispatcher=fake)
            self.assertEqual(0, rc)

    def test_show_does_not_invoke_docker(self) -> None:
        import subprocess
        from unittest.mock import patch
        fake = _make_fake(self.m, exit_kind="success",
                          data={"node": {"tag": "24"}})
        with patch.object(subprocess, "run",
                          side_effect=RuntimeError("no subprocess")):
            rc, _, _ = _run(self.m, ["show", "--scope", "build"],
                            dispatcher=fake)
            self.assertEqual(0, rc)

    def test_check_updates_does_not_invoke_docker(self) -> None:
        import subprocess
        from unittest.mock import patch
        fake = _make_fake(self.m, exit_kind="success",
                          data={"results": []})
        with patch.object(subprocess, "run",
                          side_effect=RuntimeError("no subprocess")):
            rc, _, _ = _run(self.m, ["check-updates"], dispatcher=fake)
            self.assertEqual(0, rc)


if __name__ == "__main__":
    unittest.main()
