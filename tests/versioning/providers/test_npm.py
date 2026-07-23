"""npm provider tests with fake HTTP transport."""
from __future__ import annotations

import json
import unittest

from docker.versioning.model import (
    NpmSource,
    NpmUpdate,
    UpdateTarget,
    UpdateKind,
)
from docker.versioning.providers.base import ProviderContext
from docker.versioning.providers.npm import NpmProvider
from tests.versioning.support.fake_http import FakeHttpTransport, FailingHttpTransport
from tests.versioning.support.fake_git import FakeGitTransport


class TestNpmProvider(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttpTransport()
        self.git = FakeGitTransport()
        self.provider = NpmProvider()

    def _ctx(self, include_prerelease=False):
        return ProviderContext(
            http=self.http,
            git=self.git,
            include_prerelease=include_prerelease,
            tokens={},
        )

    def _target(self, version="1.2.3", package="@scope/pkg", stable_only=True):
        return UpdateTarget(
            path="stages.pi-tools.pi",
            current=version,
            source=NpmSource(package=package),
            update=NpmUpdate(stable_only=stable_only),
            artifacts={},
        )

    def _set_versions(self, package, versions_dict):
        from urllib.parse import quote
        encoded = quote(package, safe="")
        self.http.set(
            "GET",
            f"https://registry.npmjs.org/{encoded}",
            status=200,
            body=json.dumps({"versions": versions_dict}).encode(),
        )

    def test_current_when_no_newer_version(self):
        self._set_versions("@scope/pkg", {
            "1.2.3": {"version": "1.2.3"},
            "1.2.2": {"version": "1.2.2"},
        })
        result = self.provider.discover(self._target("1.2.3"), self._ctx())
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.value, "1.2.3")

    def test_outdated_when_newer_stable(self):
        self._set_versions("@scope/pkg", {
            "1.2.3": {"version": "1.2.3"},
            "1.3.0": {"version": "1.3.0"},
        })
        result = self.provider.discover(self._target("1.2.3"), self._ctx())
        self.assertEqual(result.candidate.value, "1.3.0")

    def test_prerelease_excluded_when_stable_only(self):
        self._set_versions("@scope/pkg", {
            "1.2.3": {"version": "1.2.3"},
            "1.3.0-beta.1": {"version": "1.3.0-beta.1"},
        })
        result = self.provider.discover(
            self._target("1.2.3", stable_only=True), self._ctx()
        )
        self.assertEqual(result.candidate.value, "1.2.3")

    def test_prerelease_included_with_flag(self):
        self._set_versions("@scope/pkg", {
            "1.2.3": {"version": "1.2.3"},
            "1.3.0-beta.1": {"version": "1.3.0-beta.1"},
        })
        result = self.provider.discover(
            self._target("1.2.3", stable_only=False),
            self._ctx(include_prerelease=True),
        )
        self.assertEqual(result.candidate.value, "1.3.0-beta.1")

    def test_1_10_gt_1_9(self):
        self._set_versions("@scope/pkg", {
            "1.2.3": {"version": "1.2.3"},
            "1.9.0": {"version": "1.9.0"},
            "1.10.0": {"version": "1.10.0"},
        })
        result = self.provider.discover(self._target("1.2.3"), self._ctx())
        self.assertEqual(result.candidate.value, "1.10.0")

    def test_missing_package(self):
        self.http.set(
            "GET", "https://registry.npmjs.org/no-such-pkg",
            status=404, body=b"{}",
        )
        target = self._target(package="no-such-pkg")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.unavailable_reason)

    def test_malformed_json(self):
        self.http.set(
            "GET", "https://registry.npmjs.org/bad-pkg",
            status=200, body=b"not json",
        )
        target = self._target(package="bad-pkg")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.unavailable_reason)

    def test_no_versions(self):
        self.http.set(
            "GET", "https://registry.npmjs.org/empty-pkg",
            status=200,
            body=json.dumps({"versions": {}}).encode(),
        )
        target = self._target(package="empty-pkg")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.skipped_reason)

    def test_token_not_in_result(self):
        self._set_versions("@private/pkg", {
            "1.0.0": {"version": "1.0.0"},
            "2.0.0": {"version": "2.0.0"},
        })
        ctx = ProviderContext(
            http=self.http, git=self.git,
            include_prerelease=False,
            tokens={"NPM_TOKEN": "secret-token-123"},
        )
        target = self._target(package="@private/pkg")
        result = self.provider.discover(target, ctx)
        self.assertEqual(result.candidate.value, "2.0.0")
        # Token should appear in the request Authorization header
        self.assertEqual(len(self.http.requests), 1)
        headers = self.http.requests[0][2]
        self.assertIn("Bearer secret-token-123", headers.get("Authorization", ""))
        # Token should NOT appear in the result (output)
        self.assertNotIn("secret-token-123", str(result))

    def test_scoped_package_url_encoded(self):
        self._set_versions("@earendil-works/pi-coding-agent", {
            "1.0.0": {"version": "1.0.0"},
        })
        target = self._target(package="@earendil-works/pi-coding-agent")
        self.provider.discover(target, self._ctx())
        # Check that the URL was percent-encoded
        url = self.http.requests[0][1]
        self.assertIn("%40", url)
        self.assertIn("%2F", url)

    def test_network_error(self):
        """Unexpected transport failure produces UNAVAILABLE."""
        # Don't set up any URL — it will fail
        self.http._responses.clear()
        target = self._target(package="pkg")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.unavailable_reason)

    def test_no_downgrade_when_upstream_max_older(self):
        """Upstream max (1.0.0) below current (2.0.0) → reported CURRENT."""
        self._set_versions("some-pkg", {
            "1.0.0": {"version": "1.0.0"},
            "0.9.0": {"version": "0.9.0"},
        })
        target = self._target(package="some-pkg", version="2.0.0")
        result = self.provider.discover(target, self._ctx())
        self.assertIsNotNone(result.candidate)
        # Must report CURRENT, not the older 1.0.0
        self.assertEqual(result.candidate.value, "2.0.0")
