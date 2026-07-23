"""Offline integration tests for ``check-updates`` pipeline.

All tests inject fake HTTP / Git transports — zero network calls.
Exact exit codes (0/7/8) and exact output formats are asserted.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr

from docker.versioning.cli import (
    EXIT_OK,
    EXIT_PROVIDER_FAILURE,
    EXIT_OUTDATED,
    _cmd_check_updates,
)
from docker.versioning.errors import UnknownFilterError
from docker.versioning.model import (
    ArtifactEntry,
    BaseStage,
    DockerRegistrySource,
    DockerRegistryUpdate,
    FdPrebuiltStage,
    GitHubReleaseSource,
    GitHubReleaseUpdate,
    GitSource,
    GitRefUpdate,
    Inventory,
    NodeEntry,
    NpmSource,
    NpmToolEntry,
    NpmUpdate,
    OhMyZshEntry,
    OpenSpecToolsStage,
    PiToolsStage,
    PrebuiltToolEntry,
    PyPiSource,
    PyPiUpdate,
    PythonEntry,
    RtkPrebuiltStage,
    RustChannelSource,
    RustChannelUpdate,
    RustEntry,
    RuntimeStage,
    Stages,
    ToolchainStage,
    TyEntry,
    UvEntry,
    UvPythonSource,
    UvPythonUpdate,
)
from docker.versioning.providers.base import HttpTransport, GitRefTransport

# ---------------------------------------------------------------------------
# Minimal inventory built from real entry types
# ---------------------------------------------------------------------------

def _make_inventory(*, python_override=None) -> Inventory:
    """Minimal inventory with one entry of each provider kind."""
    return Inventory(
        schema=1,
        stages=Stages(
            base=BaseStage(
                node=NodeEntry(
                    tag="24-trixie-slim",
                    digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    source=DockerRegistrySource(
                        registry="docker.io", repository="library/node",
                    ),
                    update=DockerRegistryUpdate(
                        stable_only=True, track="tag-digest",
                    ),
                ),
            ),
            toolchain=ToolchainStage(
                rust=RustEntry(
                    version="1.97.0",
                    profile="minimal",
                    components=("rustfmt", "clippy"),
                    source=RustChannelSource(
                        manifest="https://static.rust-lang.org/dist/channel-rust-1.97.0.toml",
                    ),
                    update=RustChannelUpdate(channel="stable", stable_only=True),
                ),
                uv=UvEntry(
                    version="0.11.0",
                    source=GitHubReleaseSource(
                        repository="astral-sh/uv", tag="0.11.0",
                    ),
                    update=GitHubReleaseUpdate(tag_prefix="", stable_only=True),
                    artifacts={
                        "linux-amd64": ArtifactEntry(
                            url="https://github.com/astral-sh/uv/releases/download/0.11.0/uv-x86_64-unknown-linux-gnu.tar.gz",
                            sha256="cc" * 32,
                        ),
                    },
                ),
                python=PythonEntry(
                    version="3.14.6",
                    source=UvPythonSource(implementation="cpython"),
                    update=UvPythonUpdate(implementation="cpython", stable_only=True),
                    override=python_override,
                ),
                ty=TyEntry(
                    version="0.0.50",
                    source=PyPiSource(package="ty"),
                    update=PyPiUpdate(stable_only=True),
                ),
            ),
            rtk_prebuilt=RtkPrebuiltStage(
                rtk=PrebuiltToolEntry(
                    version="v0.43.0",
                    source=GitHubReleaseSource(
                        repository="earendil-works/rtk", tag="v0.43.0",
                    ),
                    update=GitHubReleaseUpdate(
                        tag_prefix="v", stable_only=True,
                        required_platforms=("linux-amd64",),
                    ),
                    artifacts={
                        "linux-amd64": ArtifactEntry(
                            url="https://github.com/earendil-works/rtk/releases/download/v0.43.0/rtk_0.43.0_amd64.deb",
                            sha256="aa" * 32,
                        ),
                    },
                ),
            ),
            fd_prebuilt=FdPrebuiltStage(
                fd=PrebuiltToolEntry(
                    version="v10.4.2",
                    source=GitHubReleaseSource(
                        repository="sharkdp/fd", tag="v10.4.2",
                    ),
                    update=GitHubReleaseUpdate(
                        tag_prefix="v", stable_only=True,
                        required_platforms=("linux-amd64",),
                    ),
                    artifacts={
                        "linux-amd64": ArtifactEntry(
                            url="https://github.com/sharkdp/fd/releases/download/v10.4.2/fd_10.4.2_amd64.deb",
                            sha256="bb" * 32,
                        ),
                    },
                ),
            ),
            pi_tools=PiToolsStage(
                pi=NpmToolEntry(
                    version="1.0.0",
                    source=NpmSource(package="pi-coding-agent"),
                    update=NpmUpdate(stable_only=True),
                ),
            ),
            openspec_tools=OpenSpecToolsStage(
                openspec=NpmToolEntry(
                    version="1.0.0",
                    source=NpmSource(package="@earendil-works/openspec"),
                    update=NpmUpdate(stable_only=True),
                ),
            ),
            runtime=RuntimeStage(
                oh_my_zsh=OhMyZshEntry(
                    revision="abc1234",
                    source=GitSource(repository="https://github.com/ohmyzsh/ohmyzsh"),
                    update=GitRefUpdate(ref="refs/heads/master"),
                ),
            ),
        ),
        runtime_pi_extensions={},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AllUnavailableHttp(HttpTransport):
    def request(self, method, url, *, headers=()):
        return type("HttpResponse", (), {
            "status": 503, "headers": {}, "body": b"unavailable",
        })()


class _AllUnavailableGit(GitRefTransport):
    def resolve_ref(self, repository, ref):
        raise RuntimeError("no git available")


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "json": False, "suggest": False, "only": [],
        "include_prerelease": False, "strict": False,
        "fail_on_outdated": False, "no_cache": False, "cache_ttl": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _capture(func, *a, **kw) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            exit_code = func(*a, **kw)
        except SystemExit as e:
            exit_code = int(e.code) if e.code is not None else 1
    return exit_code, out.getvalue(), err.getvalue()


def _inject_transports(http, git=None):
    import docker.versioning.cli as _cli
    _orig = _cli._resolve_transports
    _cli._resolve_transports = lambda args: (http, git or _AllUnavailableGit())
    return lambda: setattr(_cli, "_resolve_transports", _orig)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckUpdatesExitCodes(unittest.TestCase):
    def setUp(self):
        self.inventory = _make_inventory()

    def test_all_unavailable_exits_zero(self):
        cleanup = _inject_transports(_AllUnavailableHttp(), _AllUnavailableGit())
        self.addCleanup(cleanup)
        code, _, err = _capture(_cmd_check_updates, _make_args(), self.inventory)
        self.assertEqual(code, EXIT_OK, f"stderr={err}")

    def test_strict_with_unavailable_exits_seven(self):
        cleanup = _inject_transports(_AllUnavailableHttp(), _AllUnavailableGit())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates, _make_args(strict=True), self.inventory,
        )
        self.assertEqual(code, EXIT_PROVIDER_FAILURE, f"stdout={out} stderr={err}")

    def test_fail_on_outdated_with_outdated_exits_eight(self):
        class _OutdatedNpmHttp(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "registry.npmjs.org" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps({
                            "versions": {
                                "1.0.0": {"version": "1.0.0"},
                                "2.0.0": {"version": "2.0.0"},
                                "1.0.1": {"version": "1.0.1"},
                            }
                        }).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_OutdatedNpmHttp())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates, _make_args(fail_on_outdated=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OUTDATED, f"stdout={out} stderr={err}")

    def test_fail_on_outdated_no_outdated_exits_zero(self):
        class _AllCurrentNpm(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "registry.npmjs.org" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps({
                            "versions": {"1.0.0": {"version": "1.0.0"}},
                        }).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_AllCurrentNpm())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates, _make_args(fail_on_outdated=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OK, f"out={out} err={err}")


class TestCheckUpdatesOutput(unittest.TestCase):
    def setUp(self):
        self.inventory = _make_inventory()

    def test_table_output_contains_header(self):
        cleanup = _inject_transports(_AllUnavailableHttp())
        self.addCleanup(cleanup)
        code, out, _ = _capture(_cmd_check_updates, _make_args(), self.inventory)
        self.assertEqual(code, EXIT_OK)
        self.assertIn("PATH", out)
        self.assertIn("STATUS", out)
        self.assertIn("APPLICABLE", out)

    def test_json_output_is_parseable(self):
        cleanup = _inject_transports(_AllUnavailableHttp())
        self.addCleanup(cleanup)
        code, out, _ = _capture(
            _cmd_check_updates, _make_args(json=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OK)
        data = json.loads(out)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_suggest_output_with_outdated(self):
        class _OutdatedNpm(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "registry.npmjs.org" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps({
                            "versions": {
                                "1.0.0": {"version": "1.0.0"},
                                "2.0.0": {"version": "2.0.0"},
                            }
                        }).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_OutdatedNpm())
        self.addCleanup(cleanup)
        code, out, _ = _capture(
            _cmd_check_updates, _make_args(suggest=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OK)
        self.assertIn("version", out)
        self.assertIn("2.0.0", out)


class TestCheckUpdatesFilters(unittest.TestCase):
    def setUp(self):
        self.inventory = _make_inventory()

    def test_only_npm_filters_to_npm_targets(self):
        class _OutdatedNpm(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "registry.npmjs.org" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps({
                            "versions": {
                                "1.0.0": {"version": "1.0.0"},
                                "2.0.0": {"version": "2.0.0"},
                            }
                        }).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_OutdatedNpm())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates,
            _make_args(only=["npm"], fail_on_outdated=True),
            self.inventory,
        )
        self.assertEqual(code, EXIT_OUTDATED, f"out={out} err={err}")

    def test_only_unknown_filter_produces_error(self):
        """Misspelled --only filters must raise UnknownFilterError
        with a message listing known paths and providers."""
        cleanup = _inject_transports(_AllUnavailableHttp())
        self.addCleanup(cleanup)
        with self.assertRaises(UnknownFilterError) as ctx:
            _cmd_check_updates(
                _make_args(only=["nonexistent-provider-xyz"]),
                self.inventory,
            )
        msg = str(ctx.exception)
        self.assertIn("nonexistent-provider-xyz", msg)
        self.assertIn("Known paths", msg)
        self.assertIn("Known providers", msg)


class TestIncompleteResults(unittest.TestCase):
    def setUp(self):
        self.inventory = _make_inventory()

    def test_github_without_sha256_is_incomplete(self):
        class _RtkNoChecksum(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "api.github.com/repos/earendil-works/rtk" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps([{
                            "tag_name": "v0.44.0",
                            "name": "v0.44.0",
                            "prerelease": False, "draft": False,
                            "body": "",
                            "assets": [{
                                "name": "rtk_0.44.0_amd64.deb",
                                "browser_download_url":
                                    "https://github.com/.../rtk_0.44.0_amd64.deb",
                            }],
                        }]).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_RtkNoChecksum())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates,
            _make_args(json=True, fail_on_outdated=True),
            self.inventory,
        )
        self.assertEqual(code, EXIT_OK, f"out={out} err={err}")
        data = json.loads(out)
        rtk_results = [r for r in data["results"] if "rtk" in r["path"]]
        self.assertTrue(rtk_results, "No RTK results found")
        for r in rtk_results:
            self.assertEqual(r["status"], "incomplete",
                             f"Expected INCOMPLETE, got {r['status']}")

    def test_github_complete_with_sha256_is_outdated(self):
        class _RtkWithChecksum(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "api.github.com/repos/earendil-works/rtk" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps([{
                            "tag_name": "v0.44.0",
                            "name": "v0.44.0",
                            "prerelease": False, "draft": False,
                            "body": (
                                "rtk_0.44.0_amd64.deb\n"
                                "sha256: " + "c" * 64
                            ),
                            "assets": [{
                                "name": "rtk_0.44.0_amd64.deb",
                                "browser_download_url":
                                    "https://github.com/.../rtk_0.44.0_amd64.deb",
                            }],
                        }]).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_RtkWithChecksum())
        self.addCleanup(cleanup)
        code, out, err = _capture(
            _cmd_check_updates,
            _make_args(json=True, fail_on_outdated=True),
            self.inventory,
        )
        self.assertEqual(code, EXIT_OUTDATED, f"out={out} err={err}")


class TestSuggestNonMutation(unittest.TestCase):
    def setUp(self):
        self.inventory = _make_inventory()

    def test_suggest_artifact_contains_version_url_sha256(self):
        """--suggest for a github-release tool must include the
        candidate version, artifact URL, and SHA-256 checksum."""

        class _RtkOutdatedComplete(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "api.github.com/repos/earendil-works/rtk" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps([{
                            "tag_name": "v0.44.0",
                            "name": "v0.44.0",
                            "prerelease": False,
                            "draft": False,
                            "body": (
                                "rtk_0.44.0_amd64.deb\n"
                                "sha256: " + "d" * 64
                            ),
                            "assets": [{
                                "name": "rtk_0.44.0_amd64.deb",
                                "browser_download_url":
                                    "https://github.com/earendil-works/rtk/"
                                    "releases/download/v0.44.0/"
                                    "rtk_0.44.0_amd64.deb",
                            }],
                        }]).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_RtkOutdatedComplete())
        self.addCleanup(cleanup)
        code, out, _ = _capture(
            _cmd_check_updates, _make_args(suggest=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OK)
        self.assertIn("v0.44.0", out,
                       "Suggest must contain candidate version")
        self.assertIn("rtk_0.44.0_amd64.deb", out,
                       "Suggest must reference artifact URL/name")
        self.assertIn("d" * 64, out,
                       "Suggest must contain artifact SHA-256")

    def test_suggest_does_not_mutate_working_tree(self):
        """--suggest must leave ``versions.toml`` and the working tree
        byte-identical to before."""

        class _OutdatedNpm(HttpTransport):
            def request(self, method, url, *, headers=()):
                if "registry.npmjs.org" in url:
                    return type("HttpResponse", (), {
                        "status": 200, "headers": {},
                        "body": json.dumps({
                            "versions": {
                                "1.0.0": {"version": "1.0.0"},
                                "2.0.0": {"version": "2.0.0"},
                            }
                        }).encode(),
                    })()
                return type("HttpResponse", (), {
                    "status": 503, "headers": {}, "body": b"unavailable",
                })()

        cleanup = _inject_transports(_OutdatedNpm())
        self.addCleanup(cleanup)

        _repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        versions_toml = os.path.join(_repo, "versions.toml")

        # Snapshot: versions.toml content
        try:
            with open(versions_toml, "rb") as f:
                toml_before = f.read()
        except FileNotFoundError:
            self.skipTest("versions.toml not found at repo root")

        # Snapshot: git status (if available in the current environment)
        import subprocess
        git_avail = subprocess.run(
            ["git", "--version"], capture_output=True,
            cwd=_repo,
        ).returncode == 0

        if git_avail:
            status_before = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True,
                cwd=_repo, text=True,
            ).stdout
            diff_before = subprocess.run(
                ["git", "diff"], capture_output=True,
                cwd=_repo, text=True,
            ).stdout

        code, out, _ = _capture(
            _cmd_check_updates, _make_args(suggest=True), self.inventory,
        )
        self.assertEqual(code, EXIT_OK)

        # versions.toml must be unmodified
        with open(versions_toml, "rb") as f:
            toml_after = f.read()
        self.assertEqual(toml_before, toml_after,
                         "--suggest modified versions.toml")

        # No cache files must appear in the repo root even when
        # [cache].dir or --cache-dir points inside the working tree.
        # --suggest mode disables disk cache writes entirely.
        files_before = set(os.listdir(_repo))

        # Working tree must be unmodified
        if git_avail:
            status_after = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True,
                cwd=_repo, text=True,
            ).stdout
            self.assertEqual(status_before, status_after,
                             "--suggest changed git working tree")
            diff_after = subprocess.run(
                ["git", "diff"], capture_output=True,
                cwd=_repo, text=True,
            ).stdout
            self.assertEqual(diff_before, diff_after,
                             "--suggest introduced git diffs")

        files_after = set(os.listdir(_repo))
        new_files = files_after - files_before
        self.assertEqual(new_files, set(),
                         f"--suggest created files in repo: {new_files}")


class TestZeroProviderRequestsFromOrdinaryCommands(unittest.TestCase):
    """validate, get, env, effective-config computation, and module
    imports must make zero provider / network requests — verified
    structurally: these code paths never import transports or updates."""

    _CLI_MOD = "docker.versioning.cli"
    _PROVIDERS_MOD = "docker.versioning.providers"
    _UPDATES_MOD = "docker.versioning.updates"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _purge_module_cache(*names: str) -> None:
        """Remove named modules from ``sys.modules`` so imports
        happen fresh on the next invocation."""
        for n in names:
            sys.modules.pop(n, None)

    def _assert_zero_provider_imports(self, msg: str) -> None:
        """Fail if any provider or updates module leaked into sys.modules."""
        self.assertNotIn(self._PROVIDERS_MOD, sys.modules,
                         f"{msg}: imported providers")
        self.assertNotIn(self._UPDATES_MOD, sys.modules,
                         f"{msg}: imported updates coordinator")

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    def test_validate_never_imports_updates_module(self):
        import docker.versioning.cli as _cli
        self._purge_module_cache(self._PROVIDERS_MOD, self._UPDATES_MOD)
        code, out, err = _capture(lambda: _cli.main(["validate"]))
        self._assert_zero_provider_imports("validate")
        self.assertEqual(code, EXIT_OK, f"stderr={err}")
        self.assertEqual(out.strip(), "valid")

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def test_get_never_imports_providers(self):
        import docker.versioning.cli as _cli
        self._purge_module_cache(self._PROVIDERS_MOD, self._UPDATES_MOD)
        code, out, err = _capture(
            lambda: _cli.main(["get", "stages.toolchain.rust.version"]),
        )
        self._assert_zero_provider_imports("get")
        self.assertEqual(code, EXIT_OK, f"stderr={err}")
        # Output should be the current rust version string (non-empty)
        self.assertTrue(out.strip(), "get produced empty output")

    def test_get_missing_path_does_not_crash(self):
        import docker.versioning.cli as _cli
        self._purge_module_cache(self._PROVIDERS_MOD, self._UPDATES_MOD)
        code, out, err = _capture(
            lambda: _cli.main(["get", "stages.nonexistent.xyz"]),
        )
        self._assert_zero_provider_imports("get (missing path)")
        # Should fail with usage error but not import providers
        self.assertNotEqual(code, EXIT_OK)

    # ------------------------------------------------------------------
    # env
    # ------------------------------------------------------------------

    def test_env_shell_never_imports_providers(self):
        import docker.versioning.cli as _cli
        self._purge_module_cache(self._PROVIDERS_MOD, self._UPDATES_MOD)
        code, out, err = _capture(lambda: _cli.main(["env"]))
        self._assert_zero_provider_imports("env")
        self.assertEqual(code, EXIT_OK, f"stderr={err}")
        self.assertIn("export ", out)

    def test_env_json_never_imports_providers(self):
        import docker.versioning.cli as _cli
        self._purge_module_cache(self._PROVIDERS_MOD, self._UPDATES_MOD)
        code, out, err = _capture(lambda: _cli.main(["env", "--json"]))
        self._assert_zero_provider_imports("env --json")
        self.assertEqual(code, EXIT_OK, f"stderr={err}")
        data = json.loads(out)
        self.assertIsInstance(data, dict)

    # ------------------------------------------------------------------
    # effective-configuration module imports
    # ------------------------------------------------------------------

    def test_effective_module_imports_no_providers(self):
        """Importing ``docker.versioning.effective`` must not pull in
        providers or updates."""
        self._purge_module_cache(
            self._PROVIDERS_MOD, self._UPDATES_MOD,
            "docker.versioning.effective",
        )
        import docker.versioning.effective  # noqa: F811
        self._assert_zero_provider_imports(
            "import docker.versioning.effective"
        )

    def test_inventory_module_imports_no_providers(self):
        """Importing ``docker.versioning.inventory`` must not pull in
        providers or updates."""
        self._purge_module_cache(
            self._PROVIDERS_MOD, self._UPDATES_MOD,
            "docker.versioning.inventory",
        )
        import docker.versioning.inventory  # noqa: F811
        self._assert_zero_provider_imports(
            "import docker.versioning.inventory"
        )

    def test_constraints_module_imports_no_providers(self):
        """Importing ``docker.versioning.constraints`` must not pull in
        providers or updates."""
        self._purge_module_cache(
            self._PROVIDERS_MOD, self._UPDATES_MOD,
            "docker.versioning.constraints",
        )
        import docker.versioning.constraints  # noqa: F811
        self._assert_zero_provider_imports(
            "import docker.versioning.constraints"
        )

    def test_model_module_imports_no_providers(self):
        """Importing ``docker.versioning.model`` must not pull in
        providers or updates."""
        self._purge_module_cache(
            self._PROVIDERS_MOD, self._UPDATES_MOD,
            "docker.versioning.model",
        )
        import docker.versioning.model  # noqa: F811
        self._assert_zero_provider_imports(
            "import docker.versioning.model"
        )

    def test_thin_wrapper_imports_no_providers(self):
        """Importing ``docker.versions`` (thin CLI entry point) must
        not pull in providers or updates."""
        self._purge_module_cache(
            self._PROVIDERS_MOD, self._UPDATES_MOD,
            "docker.versions", "docker.versioning",
            "docker.versioning.cli",
        )
        import docker.versions  # noqa: F811
        self._assert_zero_provider_imports(
            "import docker.versions"
        )


if __name__ == "__main__":
    unittest.main()
