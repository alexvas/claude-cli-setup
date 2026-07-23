"""Coordinator tests: target traversal, check_updates, suggestions.

Uses fake providers (not real network) via injected transports.
"""
from __future__ import annotations

import json
import unittest

from docker.versioning.model import (
    ArtifactEntry,
    CandidateArtifact,
    DockerRegistrySource,
    DockerRegistryUpdate,
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
    PiExtensionEntry,
    PrebuiltToolEntry,
    PythonEntry,
    PyPiSource,
    PyPiUpdate,
    RustChannelSource,
    RustChannelUpdate,
    RustEntry,
    TyEntry,
    UvEntry,
    UvPythonSource,
    UvPythonUpdate,
    UpdateCandidate,
    UpdateKind,
    UpdateResult,
    UpdateStatus,
    UpdateTarget,
    OverridePolicy,
    BaseStage,
    ToolchainStage,
    RtkPrebuiltStage,
    FdPrebuiltStage,
    PiToolsStage,
    OpenSpecToolsStage,
    RuntimeStage,
    Stages,
)
from docker.versioning.constraints import parse_constraint
from docker.versioning.providers.base import (
    ProviderContext,
    ProviderResult,
    UpdateProvider,
)
from docker.versioning.updates import (
    build_update_targets,
    check_updates,
    render_suggestions,
    render_table,
    render_json,
    render_suggestions_json,
)
from tests.versioning.support.fake_http import FakeHttpTransport, FailingHttpTransport
from tests.versioning.support.fake_git import FakeGitTransport, FailingGitTransport


def _minimal_inventory():
    return Inventory(
        schema=1,
        stages=Stages(
            base=BaseStage(node=NodeEntry(
                tag="24-trixie-slim",
                digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                source=DockerRegistrySource(registry="docker.io", repository="library/node"),
                update=DockerRegistryUpdate(stable_only=True, track="tag-digest"),
            )),
            toolchain=ToolchainStage(
                rust=RustEntry(
                    version="1.88.0", profile="minimal",
                    components=("rustfmt", "clippy"),
                    source=RustChannelSource(manifest="https://example.com/rust.toml"),
                    update=RustChannelUpdate(channel="stable", stable_only=True),
                ),
                uv=UvEntry(
                    version="0.1.0",
                    artifacts={"linux-amd64": ArtifactEntry(url="https://example.com/uv.tar.gz", sha256="a" * 64)},
                    source=GitHubReleaseSource(repository="astral-sh/uv", tag="0.1.0"),
                    update=GitHubReleaseUpdate(stable_only=True, required_platforms=("linux-amd64",)),
                ),
                python=PythonEntry(
                    version="3.14.6",
                    source=UvPythonSource(implementation="cpython"),
                    update=UvPythonUpdate(implementation="cpython", stable_only=True),
                    override=OverridePolicy(constraint=parse_constraint(">=3.14.6"), allow_prerelease=False, scheme="numeric"),
                ),
                ty=TyEntry(
                    version="0.0.61",
                    source=PyPiSource(package="ty"),
                    update=PyPiUpdate(stable_only=True),
                ),
            ),
            rtk_prebuilt=RtkPrebuiltStage(rtk=PrebuiltToolEntry(
                version="v0.1.0",
                artifacts={"linux-amd64": ArtifactEntry(url="https://example.com/rtk.deb", sha256="a" * 64)},
                source=GitHubReleaseSource(repository="rtk-ai/rtk", tag="v0.1.0"),
                update=GitHubReleaseUpdate(stable_only=True, required_platforms=("linux-amd64",)),
            )),
            fd_prebuilt=FdPrebuiltStage(fd=PrebuiltToolEntry(
                version="v1.0.0",
                artifacts={"linux-amd64": ArtifactEntry(url="https://example.com/fd.deb", sha256="a" * 64)},
                source=GitHubReleaseSource(repository="sharkdp/fd", tag="v1.0.0"),
                update=GitHubReleaseUpdate(stable_only=True, required_platforms=("linux-amd64",)),
            )),
            pi_tools=PiToolsStage(pi=NpmToolEntry(
                version="1.0.0",
                source=NpmSource(package="@scope/pkg"),
                update=NpmUpdate(stable_only=True),
            )),
            openspec_tools=OpenSpecToolsStage(openspec=NpmToolEntry(
                version="1.0.0",
                source=NpmSource(package="@scope/openspec"),
                update=NpmUpdate(stable_only=True),
            )),
            runtime=RuntimeStage(oh_my_zsh=OhMyZshEntry(
                revision="a" * 40,
                source=GitSource(repository="https://github.com/ohmyzsh/ohmyzsh.git"),
                update=GitRefUpdate(ref="master"),
            )),
        ),
        runtime_pi_extensions={},
    )


class StubProvider:
    """A fake provider that returns a pre-configured result."""
    name = "stub"

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    def discover(self, target, context):
        if self._exc is not None:
            raise self._exc
        if self._result is not None:
            return self._result
        return ProviderResult(
            candidate=UpdateCandidate(
                value=target.current, kind=UpdateKind.VERSION, artifacts={},
            )
        )


class TestTargetTraversal(unittest.TestCase):
    def test_all_targets_present(self):
        inv = _minimal_inventory()
        targets = build_update_targets(inv)
        paths = {t.path for t in targets}
        expected = {
            "stages.base.node",
            "stages.toolchain.rust",
            "stages.toolchain.uv",
            "stages.toolchain.python",
            "stages.toolchain.ty",
            "stages.rtk-prebuilt.rtk",
            "stages.fd-prebuilt.fd",
            "stages.pi-tools.pi",
            "stages.openspec-tools.openspec",
            "stages.runtime.oh-my-zsh",
        }
        self.assertEqual(paths, expected)

    def test_deterministic_ordering(self):
        inv = _minimal_inventory()
        t1 = build_update_targets(inv)
        t2 = build_update_targets(inv)
        self.assertEqual(
            [t.path for t in t1],
            [t.path for t in t2],
        )

    def test_pi_extensions_sorted(self):
        from types import MappingProxyType
        inv = Inventory(
            schema=1,
            stages=Stages(
                base=BaseStage(node=NodeEntry(
                    tag="t", digest="sha256:" + "a" * 64,
                    source=DockerRegistrySource(registry="r", repository="p"),
                    update=DockerRegistryUpdate(stable_only=True, track="tag-digest"),
                )),
                toolchain=ToolchainStage(
                    rust=RustEntry(version="1.0.0", profile="minimal", components=(), source=RustChannelSource(manifest="u"), update=RustChannelUpdate(channel="stable", stable_only=True)),
                    uv=UvEntry(version="0.1.0", artifacts={}, source=GitHubReleaseSource(repository="r/r", tag="0.1.0"), update=GitHubReleaseUpdate(stable_only=True)),
                    python=PythonEntry(version="3.14.6", source=UvPythonSource(implementation="cpython"), update=UvPythonUpdate(implementation="cpython", stable_only=True)),
                    ty=TyEntry(version="1.0.0", source=PyPiSource(package="p"), update=PyPiUpdate(stable_only=True)),
                ),
                rtk_prebuilt=RtkPrebuiltStage(rtk=PrebuiltToolEntry(version="v1.0.0", artifacts={}, source=GitHubReleaseSource(repository="r", tag="v1.0.0"), update=GitHubReleaseUpdate(stable_only=True))),
                fd_prebuilt=FdPrebuiltStage(fd=PrebuiltToolEntry(version="v1.0.0", artifacts={}, source=GitHubReleaseSource(repository="r", tag="v1.0.0"), update=GitHubReleaseUpdate(stable_only=True))),
                pi_tools=PiToolsStage(pi=NpmToolEntry(version="1.0.0", source=NpmSource(package="p"), update=NpmUpdate(stable_only=True))),
                openspec_tools=OpenSpecToolsStage(openspec=NpmToolEntry(version="1.0.0", source=NpmSource(package="p"), update=NpmUpdate(stable_only=True))),
                runtime=RuntimeStage(oh_my_zsh=OhMyZshEntry(revision="a" * 40, source=GitSource(repository="r"), update=GitRefUpdate(ref="r"))),
            ),
            runtime_pi_extensions=MappingProxyType({
                "z-ext": PiExtensionEntry(version="1.0.0", source=NpmSource(package="z"), update=NpmUpdate(stable_only=True)),
                "a-ext": PiExtensionEntry(version="1.0.0", source=NpmSource(package="a"), update=NpmUpdate(stable_only=True)),
            }),
        )
        targets = build_update_targets(inv)
        ext_paths = [t.path for t in targets if "pi-extensions" in t.path]
        self.assertEqual(ext_paths, [
            "runtime.pi-extensions.a-ext",
            "runtime.pi-extensions.z-ext",
        ])


class TestCheckUpdates(unittest.TestCase):
    def setUp(self):
        self.http = FailingHttpTransport()
        self.git = FailingGitTransport()

    def _ctx(self, include_prerelease=False):
        return ProviderContext(
            http=self.http, git=self.git,
            include_prerelease=include_prerelease, tokens={},
        )

    def test_current(self):
        inv = _minimal_inventory()
        # All providers return current
        providers = {k: StubProvider() for k in [
            "docker-registry", "rust-channel", "github-release",
            "uv-python", "pypi", "npm", "git-ref",
        ]}
        results = check_updates(inv, providers=providers, context=self._ctx())
        for r in results:
            self.assertEqual(r.status.value, "current", f"{r.path}: {r.status}")

    def test_outdated_applicable(self):
        inv = _minimal_inventory()
        providers = {
            "docker-registry": StubProvider(),
            "rust-channel": StubProvider(),
            "github-release": StubProvider(),
            "uv-python": StubProvider(),
            "pypi": StubProvider(
                ProviderResult(candidate=UpdateCandidate(
                    value="0.0.62", kind=UpdateKind.VERSION, artifacts={},
                ))
            ),
            "npm": StubProvider(),
            "git-ref": StubProvider(),
        }
        results = check_updates(inv, providers=providers, context=self._ctx())
        ty = [r for r in results if r.path == "stages.toolchain.ty"][0]
        self.assertEqual(ty.status, UpdateStatus.OUTDATED)
        self.assertTrue(ty.applicable)
        self.assertEqual(ty.candidate, "0.0.62")

    def test_skipped_unknown_provider(self):
        inv = _minimal_inventory()
        results = check_updates(inv, providers={}, context=self._ctx())
        self.assertTrue(any(r.status == UpdateStatus.SKIPPED for r in results))

    def test_unavailable_provider_error(self):
        inv = _minimal_inventory()
        providers = {
            "docker-registry": StubProvider(),
            "rust-channel": StubProvider(),
            "github-release": StubProvider(),
            "uv-python": StubProvider(),
            "pypi": StubProvider(exc=RuntimeError("network error")),
            "npm": StubProvider(),
            "git-ref": StubProvider(),
        }
        results = check_updates(inv, providers=providers, context=self._ctx())
        ty = [r for r in results if r.path == "stages.toolchain.ty"][0]
        self.assertEqual(ty.status, UpdateStatus.UNAVAILABLE)
        self.assertIn("network error", ty.reason)

    def test_provider_exception_isolation(self):
        """One provider crashing should not stop others."""
        inv = _minimal_inventory()
        providers = {
            "docker-registry": StubProvider(exc=RuntimeError("dead!")),
            "rust-channel": StubProvider(exc=RuntimeError("dead!")),
            "github-release": StubProvider(exc=RuntimeError("dead!")),
            "uv-python": StubProvider(exc=RuntimeError("dead!")),
            "pypi": StubProvider(exc=RuntimeError("dead!")),
            "npm": StubProvider(),
            "git-ref": StubProvider(exc=RuntimeError("dead!")),
        }
        results = check_updates(inv, providers=providers, context=self._ctx())
        self.assertEqual(len(results), 10)  # All targets present
        available = [r for r in results if r.status != UpdateStatus.UNAVAILABLE]
        self.assertTrue(len(available) > 0)

    def test_only_filter_provider(self):
        inv = _minimal_inventory()
        providers = {k: StubProvider() for k in [
            "docker-registry", "rust-channel", "github-release",
            "uv-python", "pypi", "npm", "git-ref",
        ]}
        results = check_updates(inv, providers=providers, context=self._ctx(), only=("npm",))
        self.assertTrue(all(r.provider == "npm" for r in results))
        self.assertEqual(len(results), 2)  # pi-tools.pi + openspec-tools.openspec

    def test_only_filter_path(self):
        inv = _minimal_inventory()
        providers = {k: StubProvider() for k in [
            "docker-registry", "rust-channel", "github-release",
            "uv-python", "pypi", "npm", "git-ref",
        ]}
        results = check_updates(inv, providers=providers, context=self._ctx(),
                                 only=("stages.toolchain.python",))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].path, "stages.toolchain.python")

    def test_deterministic_json(self):
        inv = _minimal_inventory()
        providers = {k: StubProvider() for k in [
            "docker-registry", "rust-channel", "github-release",
            "uv-python", "pypi", "npm", "git-ref",
        ]}
        results = check_updates(inv, providers=providers, context=self._ctx())
        j1 = render_json(results)
        j2 = render_json(results)
        self.assertEqual(j1, j2)
        data = json.loads(j1)
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 10)


class TestSuggestions(unittest.TestCase):
    def test_render_suggestions_only_outdated_applicable(self):
        results = [
            UpdateResult(
                path="stages.toolchain.ty",
                provider="pypi",
                current="0.0.61",
                candidate="0.0.62",
                status=UpdateStatus.OUTDATED,
                kind=UpdateKind.VERSION,
                applicable=True,
                reason=None,
                artifacts={},
            ),
            UpdateResult(
                path="stages.toolchain.rust",
                provider="rust-channel",
                current="1.88.0",
                candidate="1.89.0",
                status=UpdateStatus.OUTDATED,
                kind=UpdateKind.VERSION,
                applicable=False,
                reason="not applicable",
                artifacts={},
            ),
            UpdateResult(
                path="stages.base.node",
                provider="docker-registry",
                current="24-trixie-slim",
                candidate="sha256:bbb...",
                status=UpdateStatus.OUTDATED,
                kind=UpdateKind.DIGEST_REFRESH,
                applicable=True,
                reason=None,
                artifacts={},
                digest="sha256:bbb...",
            ),
        ]
        output = render_suggestions(results)
        self.assertIn("0.0.62", output)
        self.assertIn("stages.toolchain.ty", output)
        self.assertIn("sha256:bbb", output)
        # Non-applicable should not appear
        self.assertNotIn("1.89.0", output)  # Rust is not applicable

    def test_render_suggestions_empty(self):
        self.assertEqual(render_suggestions([]), "\n")

    def test_render_suggestions_json(self):
        results = [
            UpdateResult(
                path="stages.toolchain.ty",
                provider="pypi",
                current="0.0.61",
                candidate="0.0.62",
                status=UpdateStatus.OUTDATED,
                kind=UpdateKind.VERSION,
                applicable=True,
                reason=None,
                artifacts={},
            ),
        ]
        output = render_suggestions_json(results)
        data = json.loads(output)
        self.assertIn("suggestions", data)
        self.assertEqual(len(data["suggestions"]), 1)


class TestTableRendering(unittest.TestCase):
    def test_table_header(self):
        results: list[UpdateResult] = []
        table = render_table(results)
        self.assertIn("PATH", table)
        self.assertIn("STATUS", table)

    def test_table_contains_results(self):
        results = [
            UpdateResult(
                path="test.path",
                provider="test",
                current="1.0.0",
                candidate="2.0.0",
                status=UpdateStatus.OUTDATED,
                kind=UpdateKind.VERSION,
                applicable=True,
                reason=None,
                artifacts={},
            ),
        ]
        table = render_table(results)
        self.assertIn("test.path", table)
        self.assertIn("2.0.0", table)
