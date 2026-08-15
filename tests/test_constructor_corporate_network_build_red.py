"""RED contracts for the Phase 2 build-time trust and proxy boundary.

These tests precede the GREEN Phase 2 implementation and define the
build-vector and Dockerfile/build-context contract for ``[corporate-trust]``
and ``[network.proxy]``:

* disabled corporate settings preserve the existing Docker build vector —
  no bundle is required and no corporate proxy argument is emitted;
* configured proxy URLs are emitted verbatim under every uppercase and
  lowercase ``HTTP_PROXY``/``HTTPS_PROXY``/``ALL_PROXY`` build argument,
  with ``NO_PROXY``/``no_proxy`` emitted only for an explicit bypass list;
* the fixed bundle has an optional build-context convention: the actual
  bundle stays untracked while a tracked placeholder keeps the
  ``.docker-local`` directory present so a missing disabled bundle never
  makes ``COPY`` fail;
* the Dockerfile validates and replaces the system trust bundle before the
  first base-stage network operation and points applicable clients at the
  final system-bundle path;
* proxy build arguments are available to build stages but never converted
  into persistent image ``ENV`` values.

Run this module before tasks 2.6-2.11 and expect failures until that
boundary exists.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docker.versioning.build_orchestration import (
    BuildRequest,
    BuildResult,
    ProcessResult,
    orchestrate_build,
)
from docker.versioning.dispatch_types import ExitKind

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL = (_REPO_ROOT / "docker-constructor.toml").read_text()

_PROXY_URL_NAMES = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)

_PROXY_ARG_NAMES = _PROXY_URL_NAMES + ("NO_PROXY", "no_proxy")


def _recording_build_executor(effects: list[str]):
    class _Exec:
        def run(self, argv: tuple[str, ...]) -> ProcessResult:
            effects.append("docker-build")
            return ProcessResult(argv=argv, return_code=0, stdout="", stderr="")

    return _Exec()


def _build_arg_pairs(args: tuple[str, ...]) -> dict[str, str]:
    """Extract ``--build-arg KEY=VALUE`` pairs into a plain dict."""
    it = iter(args)
    pairs: dict[str, str] = {}
    for token in it:
        if token == "--build-arg":
            raw = next(it)
            name, _, value = raw.partition("=")
            pairs[name] = value
    return pairs


class _BuildOrchestrationRed(unittest.TestCase):
    """Runs ``orchestrate_build`` against a real inventory + local companion."""

    def build_with_local(self, companion: str | None) -> BuildResult:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            inventory = root_path / "inventory.toml"
            inventory.write_text(_CANONICAL)
            if companion is not None:
                (root_path / "inventory.local.toml").write_text(companion)
            effects: list[str] = []
            result = orchestrate_build(BuildRequest(
                inventory_path=str(inventory),
                repo_root=str(root_path),
                confirmed=False,
                dry_run=True,
                runner=_recording_build_executor(effects),
            ))
            self.assertEqual([], effects)
            return result


class TestDisabledBuildVectorRed(_BuildOrchestrationRed):
    """Task 2.1: disabled corporate settings preserve the default vector."""

    def test_disabled_build_vector_emits_no_proxy_args(self) -> None:
        result = self.build_with_local(None)
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        pairs = _build_arg_pairs(result.build_args or ())
        for name in _PROXY_ARG_NAMES:
            self.assertNotIn(name, pairs)

    def test_disabled_trust_requires_no_bundle(self) -> None:
        # No .docker-local directory is created; an explicitly disabled
        # [corporate-trust] must not require the fixed bundle to exist.
        result = self.build_with_local("[corporate-trust]\nenabled = false\n")
        self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
        pairs = _build_arg_pairs(result.build_args or ())
        for name in _PROXY_ARG_NAMES:
            self.assertNotIn(name, pairs)


class TestConfiguredProxyBuildVectorRed(_BuildOrchestrationRed):
    """Task 2.4: configured proxy URLs under every proxy build-arg name."""

    def test_configured_proxy_emitted_under_all_proxy_arg_names(self) -> None:
        # The endpoint is copied verbatim across all six names — including
        # SOCKS schemes, which are best-effort, never reinterpreted.
        for url in (
            "http://proxy.corp.example:3128",
            "socks5h://proxy.corp.example:1080",
        ):
            with self.subTest(url=url):
                result = self.build_with_local(
                    f'[network.proxy]\nurl = "{url}"\n'
                )
                self.assertEqual(ExitKind.SUCCESS, result.exit_kind, result.message)
                pairs = _build_arg_pairs(result.build_args or ())
                for name in _PROXY_URL_NAMES:
                    self.assertEqual(url, pairs.get(name), f"wrong value for {name}")
                self.assertNotIn("NO_PROXY", pairs)
                self.assertNotIn("no_proxy", pairs)

    def test_no_proxy_emitted_only_when_explicitly_configured(self) -> None:
        configured = self.build_with_local(
            '[network.proxy]\n'
            'url = "http://proxy.corp.example:3128"\n'
            'no_proxy = "localhost,.corp.example"\n'
        )
        self.assertEqual(ExitKind.SUCCESS, configured.exit_kind, configured.message)
        pairs = _build_arg_pairs(configured.build_args or ())
        self.assertEqual("localhost,.corp.example", pairs.get("NO_PROXY"))
        self.assertEqual("localhost,.corp.example", pairs.get("no_proxy"))

        unconfigured = self.build_with_local(
            '[network.proxy]\nurl = "http://proxy.corp.example:3128"\n'
        )
        self.assertEqual(ExitKind.SUCCESS, unconfigured.exit_kind, unconfigured.message)
        pairs2 = _build_arg_pairs(unconfigured.build_args or ())
        self.assertNotIn("NO_PROXY", pairs2)
        self.assertNotIn("no_proxy", pairs2)


class TestBundleBuildContextConventionRed(unittest.TestCase):
    """Task 2.2: optional fixed-bundle convention without a missing-COPY."""

    def test_bundle_ignored_and_directory_has_tracked_placeholder(self) -> None:
        gitignore = (_REPO_ROOT / ".gitignore").read_text()
        self.assertIn(
            "corporate-ca-bundle.crt",
            gitignore,
            ".gitignore must keep the actual bundle untracked",
        )
        dockerignore = (_REPO_ROOT / ".dockerignore").read_text()
        self.assertNotIn(
            ".docker-local",
            dockerignore,
            ".dockerignore must not exclude the fixed bundle from the build context",
        )
        bundle_dir = _REPO_ROOT / ".docker-local"
        self.assertTrue(
            bundle_dir.is_dir(),
            ".docker-local placeholder directory must exist in the repository",
        )
        self.assertTrue(
            any(bundle_dir.iterdir()),
            ".docker-local needs a tracked placeholder so the directory is always present",
        )

    def test_dockerfile_uses_optional_directory_copy_not_bare_file_copy(self) -> None:
        text = (_REPO_ROOT / "Dockerfile").read_text()
        self.assertNotIn(
            "COPY .docker-local/corporate-ca-bundle.crt",
            text,
            "a bare file COPY fails when the disabled bundle is missing",
        )
        self.assertIn(
            "COPY .docker-local/",
            text,
            "the bundle must be exposed via the always-present directory convention",
        )


class TestDockerfileTrustReplacementRed(unittest.TestCase):
    """Task 2.3: enabled bundle validation and replacement before network."""

    def test_base_stage_replaces_system_trust_before_network_operations(self) -> None:
        text = (_REPO_ROOT / "Dockerfile").read_text()
        self.assertIn("/etc/ssl/certs/ca-certificates.crt", text)
        self.assertIn("BEGIN CERTIFICATE", text)
        lines = text.splitlines()
        apt_indices = [i for i, line in enumerate(lines) if "apt-get update" in line]
        trust_indices = [
            i for i, line in enumerate(lines)
            if "/etc/ssl/certs/ca-certificates.crt" in line
        ]
        self.assertTrue(apt_indices, "expected a base-stage apt-get network operation")
        self.assertTrue(
            trust_indices,
            "expected trust replacement referencing /etc/ssl/certs/ca-certificates.crt",
        )
        self.assertLess(
            trust_indices[0],
            apt_indices[0],
            "trust replacement must precede the first network operation",
        )

    def test_applicable_clients_point_at_final_system_bundle_path(self) -> None:
        text = (_REPO_ROOT / "Dockerfile").read_text()
        for var in ("SSL_CERT_FILE", "NODE_EXTRA_CA_CERTS"):
            matching = [line for line in text.splitlines() if var in line]
            self.assertTrue(matching, f"expected {var} client configuration")
            self.assertTrue(
                any("/etc/ssl/certs/ca-certificates.crt" in line for line in matching),
                f"{var} must point at the final system bundle path",
            )


class TestDockerfileProxyArgsRed(unittest.TestCase):
    """Task 2.5: proxy ARGs available to stages, never persisted as ENV."""

    def test_proxy_build_args_declared_for_all_forms(self) -> None:
        text = (_REPO_ROOT / "Dockerfile").read_text()
        for name in _PROXY_ARG_NAMES:
            self.assertIn(f"ARG {name}", text)

    def test_proxy_values_never_converted_to_image_env(self) -> None:
        text = (_REPO_ROOT / "Dockerfile").read_text()
        for name in _PROXY_ARG_NAMES:
            self.assertNotIn(f"ENV {name}", text)
