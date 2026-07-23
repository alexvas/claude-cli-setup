"""Docker Registry provider tests."""
from __future__ import annotations

import unittest

from docker.versioning.model import (
    DockerRegistrySource,
    DockerRegistryUpdate,
    UpdateTarget,
    UpdateKind,
)
from docker.versioning.providers.base import ProviderContext
from docker.versioning.providers.docker_registry import DockerRegistryProvider
from tests.versioning.support.fake_http import FakeHttpTransport
from tests.versioning.support.fake_git import FakeGitTransport


class TestDockerRegistryProvider(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttpTransport()
        self.git = FakeGitTransport()
        self.provider = DockerRegistryProvider()
        # The provider probes /v2/ for auth. Reply 200 = no auth required.
        self.http.set(
            "GET", "https://docker.io/v2/",
            status=200, body=b"{}",
        )

    def _ctx(self):
        return ProviderContext(
            http=self.http, git=self.git,
            include_prerelease=False, tokens={},
        )

    def _target(self, tag="24-trixie-slim", registry="docker.io",
                repository="library/node"):
        return UpdateTarget(
            path="stages.base.node",
            current=tag,
            source=DockerRegistrySource(registry=registry, repository=repository),
            update=DockerRegistryUpdate(stable_only=True, track="tag-digest"),
            artifacts={},
        )

    def test_unchanged_digest(self):
        upstream = "sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573"
        self.http.set(
            "GET",
            "https://docker.io/v2/library/node/manifests/24-trixie-slim",
            status=200,
            headers={"Docker-Content-Digest": upstream},
        )
        result = self.provider.discover(self._target(), self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, upstream)
        self.assertEqual(result.candidate.kind, UpdateKind.DIGEST_REFRESH)

    def test_changed_digest(self):
        upstream = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        self.http.set(
            "GET",
            "https://docker.io/v2/library/node/manifests/24-trixie-slim",
            status=200,
            headers={"Docker-Content-Digest": upstream},
        )
        result = self.provider.discover(self._target(), self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, upstream)
        self.assertEqual(result.candidate.kind, UpdateKind.DIGEST_REFRESH)

    def test_no_digest_attribute(self):
        """Provider returns the upstream digest as candidate regardless of
        whether the target carries a stored digest. Comparison is done by
        the coordinator."""
        upstream = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
        self.http.set(
            "GET",
            "https://docker.io/v2/library/node/manifests/24-trixie-slim",
            status=200,
            headers={"Docker-Content-Digest": upstream},
        )
        result = self.provider.discover(self._target(), self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, upstream)
