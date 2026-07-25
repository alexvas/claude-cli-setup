"""PyPI provider tests with fake HTTP transport."""
from __future__ import annotations

import json
import unittest

from docker.versioning.model import (
    PyPiSource,
    PyPiUpdate,
    UpdateTarget,
)
from docker.versioning.providers.base import ProviderContext
from docker.versioning.providers.pypi import PyPiProvider
from tests.versioning.support.fake_http import FakeHttpTransport
from tests.versioning.support.fake_git import FakeGitTransport


class TestPyPiProvider(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttpTransport()
        self.git = FakeGitTransport()
        self.provider = PyPiProvider()

    def _ctx(self, include_prerelease=False):
        return ProviderContext(
            http=self.http, git=self.git,
            include_prerelease=include_prerelease, tokens={},
        )

    def _target(self, version="0.0.61", package="ty", stable_only=True):
        return UpdateTarget(
            path="build.stages.toolchain.ty",
            current=version,
            source=PyPiSource(package=package),
            update=PyPiUpdate(stable_only=stable_only),
            artifacts={},
        )

    def _set_releases(self, package, releases_dict):
        self.http.set(
            "GET",
            f"https://pypi.org/pypi/{package}/json",
            status=200,
            body=json.dumps({"info": {}, "releases": releases_dict}).encode(),
        )

    def test_current_when_no_newer(self):
        self._set_releases("ty", {
            "0.0.61": [{"filename": "ty-0.0.61.tar.gz"}],
            "0.0.60": [{"filename": "ty-0.0.60.tar.gz"}],
        })
        result = self.provider.discover(self._target("0.0.61"), self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, "0.0.61")

    def test_outdated_when_newer(self):
        self._set_releases("ty", {
            "0.0.61": [{"filename": "ty-0.0.61.tar.gz"}],
            "0.0.62": [{"filename": "ty-0.0.62.tar.gz"}],
        })
        result = self.provider.discover(self._target("0.0.61"), self._ctx())
        self.assertEqual(result.candidate.value, "0.0.62")

    def test_prerelease_filtered_when_stable_only(self):
        self._set_releases("ty", {
            "0.0.61": [{"filename": "ty-0.0.61.tar.gz"}],
            "0.0.62-alpha.1": [{"filename": "ty-0.0.62-alpha.1.tar.gz"}],
        })
        result = self.provider.discover(
            self._target("0.0.61", stable_only=True), self._ctx()
        )
        self.assertEqual(result.candidate.value, "0.0.61")

    def test_yanked_releases_excluded(self):
        self._set_releases("ty", {
            "0.0.61": [{"filename": "ty-0.0.61.tar.gz"}],
            "0.0.62": [{"filename": "ty-0.0.62.tar.gz", "yanked": True}],
        })
        result = self.provider.discover(self._target("0.0.61"), self._ctx())
        self.assertEqual(result.candidate.value, "0.0.61")

    def test_package_not_found(self):
        self.http.set(
            "GET", "https://pypi.org/pypi/nonexistent/json",
            status=404, body=b"{}",
        )
        target = self._target(package="nonexistent")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.unavailable_reason)

    def test_malformed_json(self):
        self.http.set(
            "GET", "https://pypi.org/pypi/bad/json",
            status=200, body=b"not json",
        )
        target = self._target(package="bad")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.unavailable_reason)

    def test_empty_releases(self):
        self._set_releases("empty", {})
        target = self._target(package="empty")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.skipped_reason)

    def test_no_downgrade_when_upstream_max_older(self):
        """Upstream max (0.0.50) below current (2.0.0) → reported CURRENT."""
        self._set_releases("some-pkg", {
            "0.0.50": [{"filename": "a.whl", "yanked": False}],
            "0.0.1": [{"filename": "b.whl", "yanked": False}],
        })
        target = self._target(package="some-pkg", version="2.0.0")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, "2.0.0")
