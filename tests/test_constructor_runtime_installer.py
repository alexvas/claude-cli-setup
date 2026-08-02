"""RED — Protected Runtime Extension Installer (Stage 10.1–10.2).

Trust boundary (corrected):
  - ArtifactDownloader.fetch(url, dest_dir) → unverified local path
  - Integrity verification is installer-owned (over file bytes)
  - PackageInstaller.install(package, artifact_path) → from verified file

10.1: DTO validation, closed-schema projection rejection, exact
      artifact resolution, installer-owned integrity verification,
      interrupted installation, actionable failure diagnostics.

10.2: Idempotent installation, post-install identity/version
      validation, mount-prefix guard, dry-run, ownership, and
      source-contract tests.

All tests use injectable fakes — no Docker daemon, network,
subprocess, systemd, filesystem writes, or interactive stdin.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

from docker.runtime_installer import (
    ArtifactDownloader,
    ArtifactFilesystem,
    ExtensionResult,
    InstallContext,
    InstallError,
    InstallResult,
    InstallStatus,
    IntegrityError,
    MetadataNotFoundError,
    MetadataReader,
    MetadataValidationError,
    MountChecker,
    PackageInstaller,
    PrivilegeContext,
    ProjectionEntry,
    ProjectionError,
    TempWorkspace,
    exit_code_for,
    install_extensions,
    read_projection,
    validate_npm_tarball_url,
    _validate_downloaded_artifact,
)


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — immutable DTOs
# ═══════════════════════════════════════════════════════════════════════


class TestProjectionEntryFieldValidation(unittest.TestCase):
    """Full trust contract for each field of ProjectionEntry is
    enforced at construction time (``__post_init__``), covering both
    ``read_projection`` and manually-supplied DTO inputs."""

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _ok(**overrides: str) -> None:
        kwargs = {
            "package": "p", "version": "1.0.0",
            "artifact_url": _pkg_url("p", "1.0.0"),
            "artifact_integrity": _VALID_SHA256,
            "metadata_file": "package.json",
        }
        kwargs.update(overrides)
        ProjectionEntry(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _fail(**overrides: str) -> None:
        with unittest.TestCase().assertRaises(
            (ProjectionError, MetadataValidationError),
        ):
            TestProjectionEntryFieldValidation._ok(**overrides)

    # ── version ──────────────────────────────────────────────────

    def test_version_must_not_be_empty(self) -> None:
        self._fail(version="")

    def test_version_must_not_be_whitespace(self) -> None:
        self._fail(version="   ")

    def test_version_must_not_contain_slash(self) -> None:
        self._fail(version="1/2")

    def test_version_must_not_contain_backslash(self) -> None:
        self._fail(version="1\\2")

    def test_valid_version_accepted(self) -> None:
        self._ok(version="1.2.3-beta.1",
                 artifact_url=_pkg_url("p", "1.2.3-beta.1"))

    def test_prerelease_version_accepted(self) -> None:
        self._ok(version="1.0.0-rc.2",
                 artifact_url=_pkg_url("p", "1.0.0-rc.2"))

    def test_build_metadata_version_accepted(self) -> None:
        self._ok(version="1.2.3+build.20250101",
                 artifact_url=_pkg_url("p", "1.2.3"))

    def test_prerelease_with_build_accepted(self) -> None:
        self._ok(version="1.2.3-beta.1+exp.sha.5114f85",
                 artifact_url=_pkg_url("p", "1.2.3-beta.1"))

    def test_version_latest_rejected(self) -> None:
        self._fail(version="latest")

    def test_version_stable_rejected(self) -> None:
        self._fail(version="stable")

    def test_version_star_range_rejected(self) -> None:
        self._fail(version="*")

    def test_version_caret_range_rejected(self) -> None:
        self._fail(version="^1.0.0")

    def test_version_tilde_range_rejected(self) -> None:
        self._fail(version="~1.2.3")

    def test_version_gte_range_rejected(self) -> None:
        self._fail(version=">=1.0.0")

    def test_version_v_prefix_rejected(self) -> None:
        self._fail(version="v1.2.3")

    def test_version_partial_rejected(self) -> None:
        self._fail(version="1.2")

    def test_version_malformed_prerelease_rejected(self) -> None:
        self._fail(version="1.2.3-!!!")

    # ── artifact_url ─────────────────────────────────────────────

    def test_url_must_be_https(self) -> None:
        self._fail(artifact_url="http://registry.npmjs.org/p/-/p-1.0.0.tgz")

    def test_url_rejects_query_string(self) -> None:
        self._fail(
            artifact_url=
            "https://registry.npmjs.org/p/-/p-1.0.0.tgz?token=secret")

    def test_url_rejects_fragment(self) -> None:
        self._fail(
            artifact_url=
            "https://registry.npmjs.org/p/-/p-1.0.0.tgz#README")

    def test_url_rejects_missing_separator(self) -> None:
        self._fail(
            artifact_url="https://registry.npmjs.org/p/pkg-1.0.0.tgz")

    def test_url_rejects_wrong_package_path(self) -> None:
        self._fail(artifact_url="https://registry.npmjs.org/q/-/p-1.0.0.tgz",
                   package="p")

    def test_url_rejects_wrong_scope(self) -> None:
        self._fail(
            artifact_url=
            "https://registry.npmjs.org/@scope/a/-/a-1.0.0.tgz",
            package="@scope/b")

    def test_url_rejects_wrong_basename(self) -> None:
        self._fail(artifact_url="https://registry.npmjs.org/p/-/bad-1.0.0.tgz",
                   package="p")

    def test_url_rejects_wrong_version(self) -> None:
        self._fail(artifact_url="https://registry.npmjs.org/p/-/p-9.9.9.tgz",
                   version="1.0.0")

    def test_url_accepts_build_metadata_version(self) -> None:
        """Version ``1.0.0+build123`` matches URL without ``+build``
        — npm tarballs never include build metadata in filenames."""
        self._ok(version="1.0.0+build123",
                 artifact_url=_pkg_url("p", "1.0.0+build123"))

    def test_url_rejects_build_metadata_in_filename(self) -> None:
        """URL with ``+build`` in the tarball filename is invalid."""
        self._fail(
            artifact_url=
            "https://registry.npmjs.org/p/-/p-1.0.0+build.tgz",
            version="1.0.0+build")

    def test_url_accepts_prerelease(self) -> None:
        self._ok(version="1.0.0-alpha.1",
                 artifact_url=_pkg_url("p", "1.0.0-alpha.1"))

    def test_valid_url_accepted(self) -> None:
        self._ok(artifact_url=_pkg_url("p", "1.0.0"))

    # ── artifact_integrity ───────────────────────────────────────

    def test_integrity_must_have_algo_prefix(self) -> None:
        self._fail(artifact_integrity="AAAA")

    def test_integrity_unsupported_algo_rejected(self) -> None:
        self._fail(artifact_integrity="md5-AAAA")

    def test_integrity_invalid_base64_rejected(self) -> None:
        self._fail(artifact_integrity="sha256-!!!bad!!!")

    def test_integrity_wrong_length_rejected(self) -> None:
        # sha256 needs 32 bytes → 44 base64 chars; give 16 bytes
        import base64
        short = base64.b64encode(b"x" * 16).decode()
        self._fail(artifact_integrity=f"sha256-{short}")

    def test_integrity_sha256_accepted(self) -> None:
        self._ok(artifact_integrity=_VALID_SHA256)

    # ── metadata_file ────────────────────────────────────────────

    def test_metadata_file_must_not_be_absolute(self) -> None:
        self._fail(metadata_file="/etc/passwd")

    def test_metadata_file_must_not_contain_parent_segment(self) -> None:
        """``..`` as a standalone path segment is rejected."""
        self._fail(metadata_file="../etc/passwd")

    def test_metadata_file_must_not_contain_dot_segment(self) -> None:
        """``.`` as a standalone path segment is rejected."""
        self._fail(metadata_file="./package.json")

    def test_metadata_file_must_not_contain_backslash(self) -> None:
        self._fail(metadata_file="pkg\\passwd")

    def test_metadata_file_must_not_be_empty(self) -> None:
        self._fail(metadata_file="")

    def test_metadata_file_must_not_be_whitespace(self) -> None:
        self._fail(metadata_file="   ")

    def test_metadata_file_rejects_empty_segment(self) -> None:
        """``//`` produces an empty segment — rejected."""
        self._fail(metadata_file="pkg//passwd")

    def test_metadata_file_rejects_trailing_slash(self) -> None:
        self._fail(metadata_file="pkg/")

    def test_double_dot_in_metadata_name_not_traversal(self) -> None:
        """``a..b`` contains ``..`` inside a longer name — accepted."""
        self._ok(metadata_file="a..b.json")

    def test_metadata_file_normalized_escape_rejected(self) -> None:
        """``a/../../b`` normalizes above root even though no single
        segment is ``..`` at the start."""
        self._fail(metadata_file="a/b/../../c")

    def test_nested_metadata_file_accepted(self) -> None:
        self._ok(metadata_file="sub/deep/pkg.json")

    # ── package name ─────────────────────────────────────────────

    def test_package_rejects_absolute(self) -> None:
        self._fail(package="/bad",
                   artifact_url=_pkg_url("/bad", "1.0.0"))

    def test_package_rejects_backslash(self) -> None:
        self._fail(package="bad\\name",
                   artifact_url=_pkg_url("bad\\name", "1.0.0"))

    def test_package_rejects_parent_segment(self) -> None:
        self._fail(package="..")

    def test_double_dot_in_package_name_accepted(self) -> None:
        """``a..b`` as package name has no traversal — accepted."""
        self._ok(package="a..b",
                 artifact_url=_pkg_url("a..b", "1.0.0"))


class TestProjectionEntryDto(unittest.TestCase):
    """ProjectionEntry is a frozen, field-complete value object."""

    def test_all_fields_present(self) -> None:
        e = ProjectionEntry(
            package="@scope/pkg",
            version="1.2.3",
            artifact_url="https://registry.npmjs.org/@scope/pkg/-/pkg-1.2.3.tgz",
            artifact_integrity=_VALID_SHA512,
            metadata_file="package.json",
        )
        self.assertEqual("@scope/pkg", e.package)
        self.assertEqual("1.2.3", e.version)
        self.assertIn("registry.npmjs.org", e.artifact_url)
        self.assertIn("sha512-", e.artifact_integrity)
        self.assertEqual("package.json", e.metadata_file)

    def test_frozen(self) -> None:
        e = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )
        with self.assertRaises(Exception):
            e.package = "q"  # type: ignore[misc]

    def test_integrity_always_present(self) -> None:
        # Every entry must carry integrity so the installer can verify.
        e = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA512,
            metadata_file="package.json",
        )
        self.assertTrue(len(e.artifact_integrity) > 0)


class TestInstallStatusEnum(unittest.TestCase):
    """InstallStatus covers all per-extension outcomes."""

    def test_four_states(self) -> None:
        self.assertEqual(4, len(InstallStatus))

    def test_values_are_distinct(self) -> None:
        values = list(InstallStatus)
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                self.assertNotEqual(values[i], values[j])


class TestExtensionResultDto(unittest.TestCase):
    """ExtensionResult is a frozen per-extension outcome."""

    def test_success_has_no_detail(self) -> None:
        r = ExtensionResult(package="p", version="1", status=InstallStatus.OK)
        self.assertIsNone(r.detail)

    def test_failure_carries_structured_detail(self) -> None:
        r = ExtensionResult(
            package="p", version="1",
            status=InstallStatus.FAILED,
            detail="integrity mismatch: expected deadbeef, got cafebabe",
        )
        self.assertIn("integrity", r.detail or "")

    def test_already_installed_has_no_detail(self) -> None:
        r = ExtensionResult(
            package="p", version="1",
            status=InstallStatus.ALREADY_INSTALLED,
        )
        self.assertIsNone(r.detail)

    def test_frozen(self) -> None:
        r = ExtensionResult(package="p", version="1", status=InstallStatus.OK)
        with self.assertRaises(Exception):
            r.status = InstallStatus.FAILED  # type: ignore[misc]


class TestInstallResultDto(unittest.TestCase):
    """InstallResult aggregates per-extension outcomes."""

    def test_ok_when_all_succeed(self) -> None:
        result = InstallResult(results=(
            ExtensionResult(package="a", version="1", status=InstallStatus.OK),
            ExtensionResult(package="b", version="2", status=InstallStatus.OK),
        ))
        self.assertTrue(result.ok)

    def test_not_ok_when_any_fails(self) -> None:
        result = InstallResult(results=(
            ExtensionResult(package="a", version="1", status=InstallStatus.OK),
            ExtensionResult(package="b", version="2",
                            status=InstallStatus.FAILED, detail="boom"),
        ))
        self.assertFalse(result.ok)

    def test_dry_run_flag_preserved(self) -> None:
        result = InstallResult(results=(), dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertTrue(result.ok)


class TestInstallErrorHierarchy(unittest.TestCase):
    """Domain errors carry structured detail for actionable diagnostics."""

    def test_integrity_error_extends_install_error(self) -> None:
        self.assertTrue(issubclass(IntegrityError, InstallError))

    def test_integrity_error_carries_algorithm_expected_actual(self) -> None:
        exc = IntegrityError(
            "checksum mismatch",
            algorithm="sha256",
            expected="deadbeef",
            actual="cafebabe",
        )
        self.assertEqual("sha256", exc.algorithm)
        self.assertEqual("deadbeef", exc.expected)
        self.assertEqual("cafebabe", exc.actual)

    def test_projection_error_is_install_error(self) -> None:
        self.assertTrue(issubclass(ProjectionError, InstallError))

    def test_metadata_validation_error_is_install_error(self) -> None:
        self.assertTrue(issubclass(MetadataValidationError, InstallError))

    def test_metadata_not_found_error_is_install_error(self) -> None:
        self.assertTrue(issubclass(MetadataNotFoundError, InstallError))


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — read_projection: valid TOML
# ═══════════════════════════════════════════════════════════════════════


class TestReadProjectionValid(unittest.TestCase):
    """read_projection parses the Stage 5 effective runtime TOML."""

    _VALID = """\
[extensions."pi-read"]
package = "pi-read"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/pi-read/-/pi-read-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"

[extensions."pi-green-loop"]
package = "pi-green-loop"
version = "2.0.0"
artifact = { url = "https://registry.npmjs.org/pi-green-loop/-/pi-green-loop-2.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
"""

    def test_parse_two_extensions(self) -> None:
        entries = read_projection(self._tmp(self._VALID))
        self.assertEqual(2, len(entries))

    def test_fields_fully_populated(self) -> None:
        entries = read_projection(self._tmp(self._VALID))
        for e in entries:
            self.assertTrue(e.package)
            self.assertTrue(e.version)
            self.assertTrue(e.artifact_url.startswith("https://"))
            self.assertTrue(e.artifact_integrity.startswith("sha"))
            self.assertTrue(e.metadata_file)

    @staticmethod
    def _tmp(content: str) -> str:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False,
        )
        try:
            tmp.write(content)
        finally:
            tmp.close()
        return tmp.name


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — read_projection: deterministic ordering
# ═══════════════════════════════════════════════════════════════════════


class TestDeterministicOrdering(unittest.TestCase):
    """Extension entries MUST be returned in name-sorted order,
    not insertion/Toml-layout order."""

    _UNSORTED_TOML = """\
[extensions.z]
package = "z"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/z/-/z-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"

[extensions.a]
package = "a"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/a/-/a-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"

[extensions.m]
package = "m"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/m/-/m-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
"""

    def test_entries_sorted_by_name(self) -> None:
        path = _tmp_toml(self._UNSORTED_TOML)
        entries = read_projection(path)
        names = [e.package for e in entries]
        self.assertEqual(["a", "m", "z"], names)
        self.assertEqual(names, sorted(names))


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — read_projection: closed-schema rejection
# ═══════════════════════════════════════════════════════════════════════


class TestClosedSchemaRejection(unittest.TestCase):
    """read_projection must reject fields that belong to the reviewed
    source or build projection (host-only / update / override metadata)."""

    _BASE = """\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
"""

    def test_rejects_unknown_root_field(self) -> None:
        path = _tmp_toml(self._BASE + 'build = "garbage"\n')
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_rejects_unknown_extension_field(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
source = { package = "p", registry = "https://x" }
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_rejects_update_metadata(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
update = { provider = "npm", max_age_seconds = 3600 }
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_rejects_override_policy(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
override = { allow = false, message = "no" }
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_rejects_unselected_artifact_catalogs(self) -> None:
        # Only the selected artifact (matching version) is present;
        # other version entries must not appear.
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
artifacts = { "1.0.0" = { url = "https://x", integrity = "sha512-A" }, "2.0.0" = { url = "https://x", integrity = "sha512-B" } }
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — read_projection: required fields
# ═══════════════════════════════════════════════════════════════════════


class TestRequiredFields(unittest.TestCase):
    """Every projection field required by Stage 5 must be validated."""

    def test_empty_extensions_rejected(self) -> None:
        path = _tmp_toml("")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_missing_package_identity(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_missing_version(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_missing_artifact_url(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_missing_integrity(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_missing_metadata_file(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)


class TestReadProjectionWrongTypes(unittest.TestCase):
    """Each projected field must already be a TOML string;
    :func:`read_projection` rejects int, float, bool, etc."""

    _TOML_TEMPLATE = """\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = {{ url = "{_pkg_url('p', '1.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"
"""

    def _make_toml(self, **overrides: object) -> str:
        """Produce TOML with fields overridden by raw TOML fragments."""
        lines = self._TOML_TEMPLATE.splitlines(keepends=True)
        result: list[str] = []
        for line in lines:
            stripped = line.strip()
            for key, frag in overrides.items():
                if stripped.startswith(key):
                    line = f"{key} = {frag}\n"
                    break
            result.append(line)
        return "".join(result)

    def test_package_must_be_string(self) -> None:
        path = _tmp_toml(self._make_toml(package="123"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_version_must_be_string(self) -> None:
        path = _tmp_toml(self._make_toml(version="1.0"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_url_must_be_string(self) -> None:
        # Replace the entire artifact inline table with a variant
        # where url is an unquoted int.
        toml = """\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = 42, integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
"""
        path = _tmp_toml(toml)
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_integrity_must_be_string(self) -> None:
        toml = """\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = 0 }
metadata_file = "package.json"
"""
        path = _tmp_toml(toml)
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_metadata_file_must_be_string(self) -> None:
        path = _tmp_toml(self._make_toml(metadata_file="true"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_raises_projection_error_not_type_error(self) -> None:
        """Wrong-type rejections are always ProjectionError, never TypeError."""
        toml = """\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = 1, integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
"""
        path = _tmp_toml(toml)
        with self.assertRaises(ProjectionError):
            read_projection(path)


class TestReadProjectionDuplicatePackage(unittest.TestCase):
    """Duplicate package identities in the projection must be rejected
    before any installation mutations occur."""

    @staticmethod
    def _dup_base() -> str:
        return f"""\
[extensions.a]
package = "dup"
version = "1.0.0"
artifact = {{ url = "{_pkg_url('dup', '1.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"

[extensions.b]
package = "dup"
version = "2.0.0"
artifact = {{ url = "{_pkg_url('dup', '2.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"
"""

    def test_duplicate_package_rejected(self) -> None:
        path = _tmp_toml(self._dup_base())
        with self.assertRaises(ProjectionError) as ctx:
            read_projection(path)
        self.assertIn("dup", str(ctx.exception))

    def test_unique_packages_accepted(self) -> None:
        toml = f"""\
[extensions.a]
package = "x"
version = "1.0.0"
artifact = {{ url = "{_pkg_url('x', '1.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"

[extensions.b]
package = "y"
version = "2.0.0"
artifact = {{ url = "{_pkg_url('y', '2.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"
"""
        path = _tmp_toml(toml)
        entries = read_projection(path)
        self.assertEqual(2, len(entries))
        self.assertEqual(["x", "y"], [e.package for e in entries])


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — read_projection: unsafe values
# ═══════════════════════════════════════════════════════════════════════


class TestUnsafeMetadataPath(unittest.TestCase):
    """metadata_file must be a safe relative path (no traversal, no absolute)."""

    def test_traversal_rejected(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "../etc/passwd"
""")
        with self.assertRaises(MetadataValidationError):
            read_projection(path)

    def test_absolute_path_rejected(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "/etc/passwd"
""")
        with self.assertRaises(MetadataValidationError):
            read_projection(path)

    def test_relative_safe_accepted(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "pkg/package.json"
""")
        entries = read_projection(path)
        self.assertEqual("pkg/package.json", entries[0].metadata_file)


class TestPackageNameSafety(unittest.TestCase):
    """Package names become path components under node_modules.
    Reject traversal, absolute paths, backslashes, malformed scoped
    names, and extra slash components.  Accept only valid unscoped
    names or exactly ``@scope/name``.

    Validation is checked at :class:`ProjectionEntry` construction
    time, so it covers both ``read_projection`` and manually
    constructed DTO inputs."""

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _entry(package: str) -> ProjectionEntry:
        return ProjectionEntry(
            package=package, version="1.0.0",
            artifact_url=_pkg_url(package, "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )

    @staticmethod
    def _toml_entry(package: str) -> str:
        return f"""\
[extensions.p]
package = "{package}"
version = "1.0.0"
artifact = {{ url = "{_pkg_url(package, '1.0.0')}", integrity = "{_VALID_SHA256}" }}
metadata_file = "package.json"
"""

    def _assert_rejects_direct(self, package: str) -> None:
        with self.assertRaises(ProjectionError):
            self._entry(package)

    def _assert_rejects_toml(self, package: str) -> None:
        path = _tmp_toml(self._toml_entry(package))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def _assert_accepts_direct(self, package: str) -> None:
        self._entry(package)  # must not raise

    def _assert_accepts_toml(self, package: str) -> None:
        path = _tmp_toml(self._toml_entry(package))
        entries = read_projection(path)
        self.assertEqual(1, len(entries))

    # ── traversal (both paths) ───────────────────────────────────

    def test_rejects_dot_dot_direct(self) -> None:
        self._assert_rejects_direct("../etc/passwd")

    def test_rejects_dot_dot_toml(self) -> None:
        self._assert_rejects_toml("../etc/passwd")

    def test_rejects_encoded_traversal_direct(self) -> None:
        self._assert_rejects_direct("pkg/../../root")

    def test_rejects_encoded_traversal_toml(self) -> None:
        self._assert_rejects_toml("pkg/../../root")

    # ── absolute paths ───────────────────────────────────────────

    def test_rejects_absolute_path_direct(self) -> None:
        self._assert_rejects_direct("/etc/passwd")

    def test_rejects_absolute_path_toml(self) -> None:
        self._assert_rejects_toml("/etc/passwd")

    def test_rejects_relative_path_direct(self) -> None:
        self._assert_rejects_direct("./hidden")

    def test_rejects_relative_path_toml(self) -> None:
        self._assert_rejects_toml("./hidden")

    # ── backslashes ──────────────────────────────────────────────

    def test_rejects_backslash_direct(self) -> None:
        self._assert_rejects_direct("pkg\\..\\etc")

    def test_rejects_backslash_toml(self) -> None:
        self._assert_rejects_toml("pkg\\..\\etc")

    # ── malformed scoped names ───────────────────────────────────

    def test_rejects_at_only_direct(self) -> None:
        self._assert_rejects_direct("@")

    def test_rejects_scope_no_slash_direct(self) -> None:
        self._assert_rejects_direct("@scope")

    def test_rejects_scope_trailing_slash_direct(self) -> None:
        self._assert_rejects_direct("@scope/")

    def test_rejects_double_at_direct(self) -> None:
        self._assert_rejects_direct("@@scope/name")

    def test_rejects_empty_scope_direct(self) -> None:
        self._assert_rejects_direct("@/name")

    def test_rejects_empty_name_scoped_direct(self) -> None:
        self._assert_rejects_direct("@scope/")

    def test_rejects_double_slash_scoped_direct(self) -> None:
        self._assert_rejects_direct("@scope//name")

    def test_rejects_malformed_scoped_toml(self) -> None:
        self._assert_rejects_toml("@scope//evil")

    # ── extra slash components in unscoped name ──────────────────

    def test_rejects_triple_component_direct(self) -> None:
        self._assert_rejects_direct("a/b/c")

    def test_rejects_double_component_direct(self) -> None:
        self._assert_rejects_direct("scope/name")

    def test_rejects_extra_slash_toml(self) -> None:
        self._assert_rejects_toml("scope/name")

    # ── empty name ───────────────────────────────────────────────

    def test_rejects_empty_direct(self) -> None:
        self._assert_rejects_direct("")

    def test_rejects_empty_toml(self) -> None:
        self._assert_rejects_toml("")

    # ── valid unscoped names ─────────────────────────────────────

    def test_accepts_simple_unscoped_direct(self) -> None:
        self._assert_accepts_direct("pi-read")

    def test_accepts_simple_unscoped_toml(self) -> None:
        self._assert_accepts_toml("pi-read")

    def test_accepts_unscoped_with_dash_direct(self) -> None:
        self._assert_accepts_direct("my-package")

    def test_accepts_unscoped_with_underscore_direct(self) -> None:
        self._assert_accepts_direct("my_package")

    def test_accepts_unscoped_with_dot_direct(self) -> None:
        self._assert_accepts_direct("my.package")

    def test_accepts_single_char_direct(self) -> None:
        self._assert_accepts_direct("a")

    # ── valid scoped names ───────────────────────────────────────

    def test_accepts_scoped_direct(self) -> None:
        self._assert_accepts_direct("@scope/name")

    def test_accepts_scoped_toml(self) -> None:
        self._assert_accepts_toml("@scope/name")

    def test_accepts_scoped_with_dashes_direct(self) -> None:
        self._assert_accepts_direct("@earendil-works/pi-green-loop")

    def test_accepts_scoped_with_dots_direct(self) -> None:
        self._assert_accepts_direct("@scope.dot/pkg.name")

    def test_accepts_scoped_single_char_direct(self) -> None:
        self._assert_accepts_direct("@s/p")


# ═══════════════════════════════════════════════════════════════════════
# Shared semver validation
# ═══════════════════════════════════════════════════════════════════════


class TestSharedSemverValidation(unittest.TestCase):
    """The shared :mod:`docker.versioning.semver` validator rejects
    moving tags, ranges, and malformed versions; accepts exact
    semver including prerelease and build metadata."""

    @staticmethod
    def _ok(version: str) -> None:
        from docker.versioning.semver import validate
        validate(version)

    @staticmethod
    def _fail(version: str) -> None:
        from docker.versioning.semver import SemverError, validate
        try:
            validate(version)
        except SemverError:
            return
        raise AssertionError(f"expected SemverError for {version!r}")

    # ── valid ────────────────────────────────────────────────────

    def test_stable(self) -> None:
        self._ok("1.2.3")

    def test_zero_major(self) -> None:
        self._ok("0.1.0")

    def test_prerelease(self) -> None:
        self._ok("1.0.0-alpha.1")

    def test_rc(self) -> None:
        self._ok("2.0.0-rc.2")

    def test_build_metadata(self) -> None:
        self._ok("1.2.3+build.20250101")

    def test_prerelease_with_build(self) -> None:
        self._ok("1.2.3-beta.1+exp.sha.5114f85")

    def test_multi_digit(self) -> None:
        self._ok("123.456.789")

    # ── moving tags ──────────────────────────────────────────────

    def test_latest_rejected(self) -> None:
        self._fail("latest")

    def test_stable_rejected(self) -> None:
        self._fail("stable")

    def test_next_rejected(self) -> None:
        self._fail("next")

    def test_dev_rejected(self) -> None:
        self._fail("dev")

    def test_canary_rejected(self) -> None:
        self._fail("canary")

    def test_nightly_rejected(self) -> None:
        self._fail("nightly")

    def test_moving_tag_case_insensitive(self) -> None:
        self._fail("LATEST")
        self._fail("Latest")

    # ── empty / whitespace ───────────────────────────────────────

    def test_empty_rejected(self) -> None:
        self._fail("")

    def test_whitespace_rejected(self) -> None:
        self._fail("   ")

    # ── ranges ───────────────────────────────────────────────────

    def test_star_rejected(self) -> None:
        self._fail("*")

    def test_caret_rejected(self) -> None:
        self._fail("^1.0.0")

    def test_tilde_rejected(self) -> None:
        self._fail("~1.2.3")

    def test_gte_rejected(self) -> None:
        self._fail(">=1.0.0")

    def test_lt_rejected(self) -> None:
        self._fail("<2.0.0")

    def test_x_range_rejected(self) -> None:
        self._fail("1.x")

    # ── malformed ────────────────────────────────────────────────

    def test_v_prefix_rejected(self) -> None:
        self._fail("v1.2.3")

    def test_partial_rejected(self) -> None:
        self._fail("1.2")

    def test_malformed_prerelease_rejected(self) -> None:
        self._fail("1.2.3-!!!")

    def test_leading_zero_prerelease_rejected(self) -> None:
        self._fail("1.2.3-01")

    def test_slash_rejected(self) -> None:
        self._fail("1/2")

    def test_backslash_rejected(self) -> None:
        self._fail("1\\2")

    def test_arbitrary_text_rejected(self) -> None:
        self._fail("not-a-version")


class TestValidateNpmTarballUrl(unittest.TestCase):
    """The shared ``validate_npm_tarball_url`` validator enforces
    the complete npm tarball identity contract: HTTPS, exact path
    ``/<package>/-/<basename>-<version>.tgz``, no query/fragment.

    Both ``ProjectionEntry.__post_init__`` and ``read_projection``
    call this single validator to prevent installer/model drift."""

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _url(package: str, version: str, host: str = "registry.npmjs.org") -> str:
        basename = package.split("/")[-1]
        base_ver = version.split("+", 1)[0]
        return f"https://{host}/{package}/-/{basename}-{base_ver}.tgz"

    def _ok(self, url: str, package: str, version: str) -> None:
        validate_npm_tarball_url(url, package, version)

    def _fail(self, url: str, package: str, version: str) -> None:
        with self.assertRaises(ProjectionError):
            validate_npm_tarball_url(url, package, version)

    # ── valid ────────────────────────────────────────────────────

    def test_unscoped(self) -> None:
        self._ok(
            self._url("express", "4.18.2"),
            "express", "4.18.2",
        )

    def test_scoped(self) -> None:
        self._ok(
            self._url("@scope/pkg", "1.0.0"),
            "@scope/pkg", "1.0.0",
        )

    def test_pre_release_version(self) -> None:
        self._ok(
            self._url("pkg", "1.0.0-alpha.1"),
            "pkg", "1.0.0-alpha.1",
        )

    def test_build_metadata_in_version(self) -> None:
        self._ok(
            self._url("pkg", "1.0.0+build123"),
            "pkg", "1.0.0+build123",
        )

    def test_any_https_host_accepted(self) -> None:
        self._ok(
            self._url("pkg", "1.0.0", host="mirror.internal.example.com"),
            "pkg", "1.0.0",
        )

    # ── rejections: scheme ───────────────────────────────────────

    def test_http_rejected(self) -> None:
        self._fail(
            self._url("p", "1.0.0").replace("https", "http"),
            "p", "1.0.0",
        )

    def test_no_scheme_rejected(self) -> None:
        self._fail("registry.npmjs.org/p/-/p-1.0.0.tgz", "p", "1.0.0")

    # ── rejections: query / fragment ─────────────────────────────

    def test_query_string_rejected(self) -> None:
        self._fail(
            self._url("p", "1.0.0") + "?token=abc",
            "p", "1.0.0",
        )

    def test_fragment_rejected(self) -> None:
        self._fail(
            self._url("p", "1.0.0") + "#readme",
            "p", "1.0.0",
        )

    # ── rejections: path structure ───────────────────────────────

    def test_missing_dash_slash_dash(self) -> None:
        self._fail(
            "https://registry.npmjs.org/pkg/pkg-1.0.0.tgz",
            "pkg", "1.0.0",
        )

    def test_wrong_package_name_in_path(self) -> None:
        self._fail(
            self._url("other", "1.0.0"),
            "pkg", "1.0.0",
        )

    def test_wrong_scope_in_path(self) -> None:
        self._fail(
            self._url("@scope/x", "1.0.0"),
            "@scope/y", "1.0.0",
        )

    def test_right_scope_wrong_basename(self) -> None:
        """Path has correct scope but tarball filename has wrong
        basename — the path segment after ``/-/`` must match."""
        self._fail(
            "https://registry.npmjs.org/@scope/x/-/y-1.0.0.tgz",
            "@scope/x", "1.0.0",
        )

    def test_unscoped_instead_of_scoped(self) -> None:
        self._fail(
            self._url("name", "1.0.0"),
            "@scope/name", "1.0.0",
        )

    def test_scoped_instead_of_unscoped(self) -> None:
        self._fail(
            self._url("@scope/name", "1.0.0"),
            "name", "1.0.0",
        )

    def test_version_mismatch_in_filename(self) -> None:
        self._fail(
            self._url("p", "9.9.9"),
            "p", "1.0.0",
        )

    def test_basename_mismatch_in_filename(self) -> None:
        self._fail(
            self._url("p", "1.0.0").replace("/p-1.0.0", "/z-1.0.0"),
            "p", "1.0.0",
        )

    # ── rejections: build metadata ───────────────────────────────

    def test_build_metadata_stripped_from_filename(self) -> None:
        """Npm tarball filenames never include ``+build``.  A URL
        that contains it in the filename is rejected even when the
        version parameter itself carries the same build metadata."""
        self._fail(
            "https://registry.npmjs.org/pkg/-/pkg-1.0.0+build.tgz",
            "pkg", "1.0.0+build",
        )

    def test_base_version_must_match(self) -> None:
        """Build metadata is stripped in the filename but the base
        version must still match.  ``1.0.0+build1`` ≠ ``2.0.0+build2``
        because base versions differ."""
        self._fail(
            self._url("pkg", "2.0.0"),
            "pkg", "1.0.0+build1",
        )


class TestNpmTarballUrlCrossBoundary(unittest.TestCase):
    """The npm tarball URL contract is identical whether validated at
    the model boundary (:func:`~docker.versioning.model._validate_npm_tarball_url`)
    or the installer boundary (:func:`~docker.runtime_installer.validate_npm_tarball_url`).

    Both MUST produce the same accept/reject decisions for the same
    *(url, package, version)* triple."""

    _CASES: list[tuple[bool, str, str, str, str]] = [
        # (accept, url, package, version, label)
        (True,  "https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                "pkg", "1.0.0", "unscoped"),
        (True,  "https://registry.npmjs.org/@s/n/-/n-1.0.0.tgz",
                "@s/n", "1.0.0", "scoped"),
        (True,  "https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                "pkg", "1.0.0+build99", "build stripped"),
        (True,  "https://mirror.example.com/pkg/-/pkg-1.0.0.tgz",
                "pkg", "1.0.0", "mirror host"),
        (False, "http://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                "pkg", "1.0.0", "non-HTTPS"),
        (False, "https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz?x",
                "pkg", "1.0.0", "query string"),
        (False, "https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz#x",
                "pkg", "1.0.0", "fragment"),
        (False, "https://registry.npmjs.org/pkg/pkg-1.0.0.tgz",
                "pkg", "1.0.0", "missing /-/"),
        (False, "https://registry.npmjs.org/pkg/-/pkg-1.0.0+build.tgz",
                "pkg", "1.0.0+build", "+build in filename"),
        (False, "https://registry.npmjs.org/other/-/pkg-1.0.0.tgz",
                "pkg", "1.0.0", "wrong package path"),
        (False, "https://registry.npmjs.org/pkg/-/wrong-1.0.0.tgz",
                "pkg", "1.0.0", "wrong basename"),
        (False, "https://registry.npmjs.org/pkg/-/pkg-9.9.9.tgz",
                "pkg", "1.0.0", "wrong version"),
    ]

    def test_all_cases_match_at_both_boundaries(self) -> None:
        """Every (accept, url, package, version) case produces the
        same decision at the shared module, model boundary, and
        installer boundary."""
        from docker.versioning.npm_tarball import (
            NpmTarballUrlError,
            validate as _shared_validate,
        )
        from docker.versioning.model import (
            InvalidArtifactKey,
            _validate_npm_tarball_url as _model_validate,
        )
        for accept, url, pkg, ver, label in self._CASES:
            with self.subTest(case=label):
                shared_ok = model_ok = installer_ok = False

                try:
                    _shared_validate(url, pkg, ver)
                    shared_ok = True
                except NpmTarballUrlError:
                    pass

                try:
                    _model_validate(url, pkg, ver)
                    model_ok = True
                except InvalidArtifactKey:
                    pass

                try:
                    validate_npm_tarball_url(url, pkg, ver)
                    installer_ok = True
                except ProjectionError:
                    pass

                self.assertEqual(
                    accept, shared_ok,
                    f"shared module: expected accept={accept} "
                    f"for {label}",
                )
                self.assertEqual(
                    shared_ok, model_ok,
                    f"model disagrees with shared module on {label}",
                )
                self.assertEqual(
                    shared_ok, installer_ok,
                    f"installer disagrees with shared module on {label}",
                )


class TestUnsafeArtifactUrl(unittest.TestCase):
    """Artifact URL must be HTTPS and match package+version in path."""

    def test_non_https_rejected(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "http://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_package_version_mismatch_in_url(self) -> None:
        path = _tmp_toml("""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = { url = "https://registry.npmjs.org/p/-/p-9.9.9.tgz", integrity = "sha256-ypeBEsobvcr6wjGzmiPcTaeG7/gUfE5yuYB3ha/uSLs=" }
metadata_file = "package.json"
""")
        with self.assertRaises(ProjectionError):
            read_projection(path)


class TestUnsafeIntegrity(unittest.TestCase):
    """SRI integrity must be well-formed and use a supported algorithm."""

    def _entry_for(self, integrity: str) -> str:
        return f"""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = {{ url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "{integrity}" }}
metadata_file = "package.json"
"""

    def test_malformed_sri_no_dash(self) -> None:
        path = _tmp_toml(self._entry_for("sha512AAAA"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_unsupported_algorithm(self) -> None:
        path = _tmp_toml(self._entry_for("md5-AAAA"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_invalid_base64(self) -> None:
        path = _tmp_toml(self._entry_for("sha512-!!!invalid!!!"))
        with self.assertRaises(ProjectionError):
            read_projection(path)

    def test_wrong_digest_length_for_algorithm(self) -> None:
        # sha256 needs 32 bytes = 44 base64 chars
        too_short = base64.b64encode(b"x" * 16).decode()
        path = _tmp_toml(self._entry_for(f"sha256-{too_short}"))
        with self.assertRaises(ProjectionError):
            read_projection(path)


_VALID_SHA256 = "sha256-" + base64.b64encode(
    hashlib.sha256(b"a").digest()
).decode()
_VALID_SHA384 = "sha384-" + base64.b64encode(
    hashlib.sha384(b"a").digest()
).decode()
_VALID_SHA512 = "sha512-" + base64.b64encode(
    hashlib.sha512(b"a").digest()
).decode()


class TestValidIntegrityAlgorithms(unittest.TestCase):
    """sha256, sha384, sha512 are accepted."""

    def _entry(self, integrity: str) -> str:
        return f"""\
[extensions.p]
package = "p"
version = "1.0.0"
artifact = {{ url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz", integrity = "{integrity}" }}
metadata_file = "package.json"
"""

    def test_sha256_accepted(self) -> None:
        entries = read_projection(_tmp_toml(self._entry(_VALID_SHA256)))
        self.assertEqual(1, len(entries))

    def test_sha384_accepted(self) -> None:
        entries = read_projection(_tmp_toml(self._entry(_VALID_SHA384)))
        self.assertEqual(1, len(entries))

    def test_sha512_accepted(self) -> None:
        entries = read_projection(_tmp_toml(self._entry(_VALID_SHA512)))
        self.assertEqual(1, len(entries))


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Exact artifact resolution
# ═══════════════════════════════════════════════════════════════════════


class TestExactArtifactResolution(unittest.TestCase):
    """The downloader receives exactly the projected URL (no integrity).
    The installer receives the exact verified local artifact path.
    No registry queries, no fallback artifacts, no URL construction."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_downloader_receives_exact_url(self) -> None:
        url = "https://registry.npmjs.org/@s/p/-/p-1.0.0.tgz"
        entries = [ProjectionEntry(
            package="@s/p", version="1.0.0",
            artifact_url=url, artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        recorded = self.ctx.download._last_call  # type: ignore[attr-defined]
        self.assertEqual(url, recorded["url"])

    def test_downloader_never_receives_integrity(self) -> None:
        """The integrity value must never be passed to the downloader —
        it is installer-owned."""
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        recorded = self.ctx.download._last_call  # type: ignore[attr-defined]
        self.assertNotIn("integrity", recorded)

    def test_no_fallback_artifact_attempted(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("404"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(1, self.ctx.download.call_count)  # type: ignore[attr-defined]

    def test_installer_receives_verified_bytes_not_path(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        recorded = self.ctx.installer._last_call  # type: ignore[attr-defined]
        self.assertEqual("p", recorded["package"])
        # The installer receives verified bytes, not a mutable path.
        self.assertIn("artifact_bytes_len", recorded)
        self.assertNotIn("artifact_path", recorded,
                          "installer must not receive a mutable file path")
        self.assertNotIn("url", recorded)
        self.assertNotIn("version", recorded)

    def test_installer_never_queries_registries(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        recorded = self.ctx.installer._last_call  # type: ignore[attr-defined]
        for val in recorded.values():
            self.assertNotIn("registry", str(val).lower())
            self.assertNotIn("npmjs", str(val).lower())


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Installer-owned integrity verification
# ═══════════════════════════════════════════════════════════════════════


class TestInstallerOwnedIntegrity(unittest.TestCase):
    """Integrity verification is performed by the installer module
    over the downloaded bytes — the downloader never sees the
    expected checksum, and bytes cannot be swapped after verification."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    # ── The downloader provides UNVERIFIED bytes ────────────────────

    def test_downloader_does_not_know_integrity(self) -> None:
        """fetch() signature accepts url and dest_dir — no integrity param."""
        sig = inspect.signature(ArtifactDownloader.fetch)
        self.assertNotIn("integrity", sig.parameters,
                         "ArtifactDownloader.fetch must not accept integrity")

    # ── Integrity rejection (installer-owned) ───────────────────────

    def test_wrong_digest_fails(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        # Use a deliberately wrong expected integrity
        wrong_integrity = "sha256-" + base64.b64encode(
            hashlib.sha256(b"WRONG").digest()
        ).decode()
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=wrong_integrity,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)
        self.assertIn("integrity", (result.results[0].detail or "").lower())

    def test_integrity_failure_blocks_installer(self) -> None:
        wrong = "sha256-" + base64.b64encode(
            hashlib.sha256(b"WRONG").digest()
        ).decode()
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=wrong,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(
            0, self.ctx.installer.call_count,  # type: ignore[attr-defined]
            "installer must not be called when integrity fails",
        )

    def test_empty_download_rejected(self) -> None:
        self.ctx.file._set_bytes(b"")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)

    def test_integrity_ok_allows_install(self) -> None:
        # Download bytes whose hash matches the projected integrity
        expected = "sha256-" + base64.b64encode(
            hashlib.sha256(_dummy_bytes).digest()
        ).decode()
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=expected,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertGreater(
            self.ctx.installer.call_count, 0,  # type: ignore[attr-defined]
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Call-order recording
# ═══════════════════════════════════════════════════════════════════════


class TestCallOrderRecording(unittest.TestCase):
    """Order: load → mount → metadata-check → download →
    (integrity-verify by installer) → install → post-validate."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_call_order_matches_contract(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")

        order = self.ctx._call_log  # type: ignore[attr-defined]
        self.assertIn("mount_check", order)
        mount_idx = order.index("mount_check")
        self.assertIn("metadata.read", order)
        meta_idx = order.index("metadata.read")
        self.assertGreater(meta_idx, mount_idx)
        # download and install are skipped because already installed
        self.assertNotIn("download", order)
        self.assertNotIn("install", order)

    def test_download_before_install_when_not_cached(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")

        order = self.ctx._call_log  # type: ignore[attr-defined]
        dl_idx = order.index("download")
        inst_idx = order.index("install")
        self.assertLess(dl_idx, inst_idx,
                        "download must precede install")

    def test_install_before_post_validate(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")

        order = self.ctx._call_log  # type: ignore[attr-defined]
        inst_idx = order.index("install")
        # Post-install metadata read must come after install
        meta_indices = [i for i, name in enumerate(order)
                        if name == "metadata.read"]
        # First read is pre-check (not installed), second is post-install
        post_idx = meta_indices[-1]
        self.assertLess(inst_idx, post_idx,
                        "install must precede post-install metadata read")


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Download failures
# ═══════════════════════════════════════════════════════════════════════


class TestDownloadFailures(unittest.TestCase):
    """Download failures produce bounded, actionable diagnostics."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_connection_failure_in_diagnostics(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("connection refused: registry.npmjs.org:443"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIn("connection refused",
                      (result.results[0].detail or "").lower())

    def test_http_failure_in_diagnostics(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("HTTP 404 Not Found: https://example.com/pkg.tgz"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIn("404", result.results[0].detail or "")

    def test_timeout_in_diagnostics(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("download timed out after 30s"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIn("time", (result.results[0].detail or "").lower())

    def test_diagnostics_include_package_and_version(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("gone"),
        )
        entries = [ProjectionEntry(
            package="@scope/p", version="2.3.4",
            artifact_url=_pkg_url("@scope/p", "2.3.4"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        detail = result.results[0].detail or ""
        self.assertIn("@scope/p", detail)
        self.assertIn("2.3.4", detail)


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Interrupted installation
# ═══════════════════════════════════════════════════════════════════════


class TestInterruptedInstallation(unittest.TestCase):
    """Interruption must never write a "validated" marker or report OK."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_installer_failure_reported_as_failed(self) -> None:
        self.ctx.installer._fail_with(  # type: ignore[attr-defined]
            InstallError("pi install exited 1"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_installer_failure_never_reports_ok_for_that_extension(self) -> None:
        self.ctx.installer._fail_with(  # type: ignore[attr-defined]
            InstallError("segfault"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_metadata_read_failure_after_install_reports_failed(self) -> None:
        self.ctx.metadata._fail_on_all_reads(  # type: ignore[attr-defined]
            InstallError("package.json not found"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Downloaded path trust boundary
# ═══════════════════════════════════════════════════════════════════════


class TestDownloadedPathTrust(unittest.TestCase):
    """Before the installer reads, hashes, or installs a downloaded
    artifact, it MUST validate that the path returned by
    ``ArtifactDownloader.fetch`` is safe.

    All filesystem queries go through the injected
    ``ArtifactFilesystem`` boundary so that the validation is
    proved purely in-memory without real filesystem state.
    """

    _WS = "/var/tmp/pi-workspace-0001"

    def setUp(self) -> None:
        self._fs = _FakeArtifactFilesystem()

    # ── helpers ──────────────────────────────────────────────────

    def _ok(self, path: str) -> str:
        return _validate_downloaded_artifact(self._fs, self._WS, path)

    def _fail(self, path: str) -> None:
        with self.assertRaises(InstallError):
            self._ok(path)

    # ── valid ────────────────────────────────────────────────────

    def test_absolute_regular_file_inside_workspace_accepted(self) -> None:
        artifact = f"{self._WS}/artifact.tgz"
        self._fs._register_file(artifact)
        resolved = self._ok(artifact)
        self.assertEqual(artifact, resolved)

    # ── rejections ───────────────────────────────────────────────

    def test_relative_path_rejected(self) -> None:
        self._fail("artifact.tgz")

    def test_path_outside_workspace_rejected(self) -> None:
        outside = "/etc/passwd"
        self._fs._register_file(outside)
        self._fail(outside)

    def test_nonexistent_path_rejected(self) -> None:
        # Never registered → lstat_mode raises FileNotFoundError
        self._fail(f"{self._WS}/missing.tgz")

    def test_directory_rejected(self) -> None:
        import stat
        d = f"{self._WS}/subdir"
        self._fs._stat_map[d] = (stat.S_IFDIR | 0o755, d)
        self._fail(d)

    def test_symlink_even_inside_workspace_rejected(self) -> None:
        """All symlinks are rejected — accepting and resolving
        preserves a TOCTOU path-swap window."""
        link = f"{self._WS}/link.tgz"
        self._fs._register_symlink(link, real_target=f"{self._WS}/real.tgz")
        self._fs._register_file(f"{self._WS}/real.tgz")
        self._fail(link)

    def test_symlink_outside_workspace_rejected(self) -> None:
        link = f"{self._WS}/escape.tgz"
        self._fs._register_symlink(link, real_target="/etc/passwd")
        self._fs._register_file("/etc/passwd")
        self._fail(link)

    def test_dangling_symlink_rejected(self) -> None:
        link = f"{self._WS}/dangle.tgz"
        self._fs._register_symlink(
            link, real_target="/nonexistent/path",
        )
        self._fail(link)

    def test_fifo_rejected(self) -> None:
        import stat
        fifo = f"{self._WS}/pipe"
        self._fs._stat_map[fifo] = (stat.S_IFIFO | 0o644, fifo)
        self._fail(fifo)


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Artifact lifecycle (read / install / remove)
# ═══════════════════════════════════════════════════════════════════════


class TestArtifactLifecycle(unittest.TestCase):
    """The downloaded artifact file is read for hashing, the verified
    path is passed to install, and the file is removed on every exit
    path (success, integrity failure, install failure, interruption)."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()
        self.expected = "sha256-" + base64.b64encode(
            hashlib.sha256(_dummy_bytes).digest()
        ).decode()

    def _entry(self) -> ProjectionEntry:
        return ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=self.expected,
            metadata_file="package.json",
        )

    def _artifact_path(self) -> str:
        """Path returned by the fake downloader for the first fetch.

        Derived from the fake workspace path — not hard-coded."""
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        return f"{ws._created[0]}/artifact.tgz"

    # ── read_bytes → install chain ────────────────────────────────

    def test_file_read_before_install(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        order = self.ctx._call_log  # type: ignore[attr-defined]
        read_idx = order.index("file.read_bytes")
        inst_idx = order.index("install")
        self.assertLess(read_idx, inst_idx,
                        "file.read_bytes must precede install")

    def test_verified_bytes_passed_to_install(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        # Verify the installer received bytes (not a mutable path).
        recorded = self.ctx.installer._last_call  # type: ignore[attr-defined]
        self.assertIn("artifact_bytes_len", recorded)
        self.assertNotIn("artifact_path", recorded,
                         "installer must not receive a mutable file path — "
                         "TOCTOU between read and install is closed")
        self.assertEqual(
            len(_dummy_bytes), recorded["artifact_bytes_len"],
            "installer must receive the exact bytes that were verified",
        )

    # ── removal on success ────────────────────────────────────────

    def test_artifact_removed_after_successful_install(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self.assertIn(
            self._artifact_path(),
            self.ctx.file._removed,  # type: ignore[attr-defined]
            "artifact must be removed after successful install",
        )

    def test_removal_happens_after_install(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        order = self.ctx._call_log  # type: ignore[attr-defined]
        inst_idx = order.index("install")
        rm_idx = order.index("file.remove")
        self.assertLess(inst_idx, rm_idx,
                        "install must precede artifact removal")

    # ── removal on integrity failure ──────────────────────────────

    def test_artifact_removed_on_integrity_failure(self) -> None:
        wrong_integrity = "sha256-" + base64.b64encode(
            hashlib.sha256(b"WRONG").digest()
        ).decode()
        entry = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=wrong_integrity,
            metadata_file="package.json",
        )
        install_extensions(
            self.ctx, entries=[entry], pi_home="/mnt/pi",
        )
        self.assertIn(
            self._artifact_path(),
            self.ctx.file._removed,  # type: ignore[attr-defined]
            "artifact must be removed after integrity failure",
        )

    # ── removal on install failure ────────────────────────────────

    def test_artifact_removed_on_install_failure(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)     # type: ignore[attr-defined]
        self.ctx.installer._fail_with(              # type: ignore[attr-defined]
            InstallError("pi install crashed"),
        )
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self.assertIn(
            self._artifact_path(),
            self.ctx.file._removed,  # type: ignore[attr-defined]
            "artifact must be removed after install failure",
        )

    # ── removal on interruption (downloader raises mid-sequence) ──

    def test_artifact_removed_on_download_interruption(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("connection lost mid-download"),
        )
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        # No file was created, but remove should be a no-op.
        self.assertFalse(self.ctx.file._fail_remove)  # type: ignore[attr-defined]

    # ── read failure surface ──────────────────────────────────────

    def test_file_read_failure_surfaces_as_install_error(self) -> None:
        self.ctx.file._fail_read = True  # type: ignore[attr-defined]
        result = install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    # ── TOCTOU gap minified ─────────────────────────────────────────

    def test_install_receives_verified_bytes_not_mutable_path(self) -> None:
        """The installer receives the exact bytes that were verified,
        not a filesystem path that could be replaced between
        read_bytes and install.  This minifies the TOCTOU window
        identified in Stage 10.5 item 62. TOCTOU would be closed
        with materialize-runtime-artifacts-on-host change impementation"""
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        recorded = self.ctx.installer._last_call  # type: ignore[attr-defined]
        self.assertIn(
            "artifact_bytes_len", recorded,
            "installer must receive artifact_bytes, not artifact_path",
        )
        self.assertNotIn(
            "artifact_path", recorded,
            "installer must NEVER receive a filesystem path — "
            "the file could have been replaced between read and install",
        )

    def test_bytes_match_read_content(self) -> None:
        """The bytes passed to install are exactly the bytes returned
        by read_bytes — not a re-read from a potentially mutated file."""
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        recorded = self.ctx.installer._last_call  # type: ignore[attr-defined]
        self.assertEqual(
            len(_dummy_bytes), recorded["artifact_bytes_len"],
            "install bytes must have the exact length of the verified content",
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Temp workspace lifecycle
# ═══════════════════════════════════════════════════════════════════════


class TestTempWorkspaceLifecycle(unittest.TestCase):
    """A unique, collision-safe private temp directory is created
    before download and cleaned up on every exit path: success,
    integrity failure, install failure, and interruption."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()
        self._valid = "sha256-" + base64.b64encode(
            hashlib.sha256(_dummy_bytes).digest()
        ).decode()

    def _entry(self) -> ProjectionEntry:
        return ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=self._valid,
            metadata_file="package.json",
        )

    def _assert_workspace_cleaned_up(self) -> None:
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        self.assertGreater(len(ws._created), 0,
                           "workspace must be created")
        for path in ws._created:
            self.assertIn(
                path, ws._cleaned,
                f"workspace {path!r} must be cleaned up",
            )

    # ── creation ─────────────────────────────────────────────────

    def test_workspace_created_before_download(self) -> None:
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        order = self.ctx._call_log  # type: ignore[attr-defined]
        ws_idx = order.index("workspace.create")
        dl_idx = order.index("download")
        self.assertLess(ws_idx, dl_idx,
                        "workspace.create must precede download")

    def test_workspace_path_is_absolute(self) -> None:
        """Every workspace path returned by create() is absolute."""
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        path1 = ws.create()
        path2 = ws.create()
        self.assertTrue(os.path.isabs(path1),
                        f"workspace path must be absolute: {path1!r}")
        self.assertTrue(os.path.isabs(path2),
                        f"workspace path must be absolute: {path2!r}")
        ws.cleanup(path1)
        ws.cleanup(path2)

    def test_workspace_path_is_unique(self) -> None:
        """No two create() calls return the same path."""
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        paths = [ws.create() for _ in range(5)]
        self.assertEqual(len(paths), len(set(paths)),
                         f"workspace paths must be unique, got: {paths}")
        for p in paths:
            ws.cleanup(p)

    def test_workspace_contract_privacy_clause(self) -> None:
        """The TempWorkspace docstring mandates owner-only (0o700)
        permissions so downloaded artifacts are never world-readable."""
        doc = TempWorkspace.__doc__ or ""
        self.assertIn("0o700", doc,
                       "TempWorkspace must document 0o700 mode")
        self.assertIn("Owner-only", doc,
                       "TempWorkspace must document owner-only privacy")

    def test_workspace_has_owner_only_permissions(self) -> None:
        """A workspace created by a real TempWorkspace MUST have
        owner-only permissions (0o700).  This test exercises the
        real boundary, not the fake — it proves the behavioral
        contract, not just the docstring."""
        ws = InstallContext.real_workspace()
        path = ws.create()
        try:
            self.assertTrue(os.path.isabs(path),
                            f"workspace path must be absolute: {path!r}")
            stat = os.stat(path)
            actual = stat.st_mode & 0o777
            self.assertEqual(
                0o700, actual,
                f"workspace must be owner-only (0o700), "
                f"got {actual:#o}: {path!r}",
            )
        finally:
            ws.cleanup(path)

    def test_two_extensions_get_same_workspace(self) -> None:
        """A single install_extensions call reuses the workspace."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="a", version="1.0.0",
        )
        entries = [
            ProjectionEntry(
                package="a", version="1.0.0",
                artifact_url=_pkg_url("a", "1.0.0"), artifact_integrity=self._valid,
                metadata_file="p.json",
            ),
            ProjectionEntry(
                package="b", version="2.0.0",
                artifact_url=_pkg_url("b", "2.0.0"), artifact_integrity=self._valid,
                metadata_file="p.json",
            ),
        ]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        self.assertEqual(1, ws._counter,
                         "single install_extensions call creates one workspace")

    # ── cleanup on success ───────────────────────────────────────

    def test_workspace_cleaned_up_on_success(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self._assert_workspace_cleaned_up()

    def test_workspace_cleanup_after_file_removal(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)  # type: ignore[attr-defined]
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        order = self.ctx._call_log  # type: ignore[attr-defined]
        file_rm = order.index("file.remove")
        ws_clean = order.index("workspace.cleanup")
        self.assertLess(file_rm, ws_clean,
                        "file.remove must precede workspace.cleanup")

    # ── cleanup on integrity failure ─────────────────────────────

    def test_workspace_cleaned_up_on_integrity_failure(self) -> None:
        wrong = "sha256-" + base64.b64encode(
            hashlib.sha256(b"WRONG").digest()
        ).decode()
        entry = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=wrong,
            metadata_file="package.json",
        )
        install_extensions(
            self.ctx, entries=[entry], pi_home="/mnt/pi",
        )
        self._assert_workspace_cleaned_up()

    # ── cleanup on install failure ───────────────────────────────

    def test_workspace_cleaned_up_on_install_failure(self) -> None:
        self.ctx.file._set_bytes(_dummy_bytes)     # type: ignore[attr-defined]
        self.ctx.installer._fail_with(              # type: ignore[attr-defined]
            InstallError("pi install crashed"),
        )
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self._assert_workspace_cleaned_up()

    # ── cleanup on download interruption ─────────────────────────

    def test_workspace_cleaned_up_on_download_failure(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("connection refused"),
        )
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
        )
        self._assert_workspace_cleaned_up()

    # ── dry-run ──────────────────────────────────────────────────

    def test_dry_run_skips_workspace_creation(self) -> None:
        install_extensions(
            self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
            dry_run=True,
        )
        ws = self.ctx.workspace  # type: ignore[attr-defined]
        self.assertEqual(0, ws._counter,
                         "dry-run must not create temp workspace")

    # ── creation failure ─────────────────────────────────────────

    def test_workspace_creation_failure_surfaces(self) -> None:
        self.ctx.workspace._fail_create = True  # type: ignore[attr-defined]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=[self._entry()], pi_home="/mnt/pi",
            )


# ═══════════════════════════════════════════════════════════════════════
# 10.1 — Package process failures
# ═══════════════════════════════════════════════════════════════════════


class TestPackageProcessFailures(unittest.TestCase):
    """Installer process failures produce diagnostics with bounded output."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_executable_missing_diagnostic(self) -> None:
        self.ctx.installer._fail_with(  # type: ignore[attr-defined]
            InstallError("executable 'pi' not found on PATH"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIn("pi", (result.results[0].detail or "").lower())

    def test_nonzero_status_diagnostic(self) -> None:
        self.ctx.installer._fail_with(  # type: ignore[attr-defined]
            InstallError("pi install returned exit code 2: stderr output"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIn("exit code", (result.results[0].detail or "").lower())

    def test_diagnostics_include_package_and_version(self) -> None:
        self.ctx.installer._fail_with(  # type: ignore[attr-defined]
            InstallError("installation failed"),
        )
        entries = [ProjectionEntry(
            package="@x/y", version="3.0.0",
            artifact_url=_pkg_url("@x/y", "3.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        detail = result.results[0].detail or ""
        self.assertIn("@x/y", detail)
        self.assertIn("3.0.0", detail)


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Idempotent installation
# ═══════════════════════════════════════════════════════════════════════


class TestIdempotentInstallation(unittest.TestCase):
    """Already-correctly-installed packages must be skipped entirely."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_already_installed_returns_already_status(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )

    def test_already_installed_skips_download_and_install(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(0, self.ctx.download.call_count)  # type: ignore[attr-defined]
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Already-matching package (spec 23)
# ═══════════════════════════════════════════════════════════════════════


class TestAlreadyMatchingPackage(unittest.TestCase):
    """When metadata name+version match the projection exactly,
    no download/install occurs and ALREADY_INSTALLED is reported."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_metadata_name_equals_projected_package(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )

    def test_metadata_version_equals_projected_version(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="3.2.1",
        )
        entries = [ProjectionEntry(
            package="p", version="3.2.1",
            artifact_url=_pkg_url("p", "3.2.1"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )

    def test_already_matching_triggers_no_download(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(0, self.ctx.download.call_count)  # type: ignore[attr-defined]

    def test_already_matching_triggers_no_install(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    def test_already_matching_outcome_is_already_installed(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Mismatched installed packages
# ═══════════════════════════════════════════════════════════════════════


class TestMismatchedInstalledPackages(unittest.TestCase):
    """Version/name mismatch after install must be reported as FAILED."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_version_mismatch_is_failure(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="0.9.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_name_mismatch_is_always_failure(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="good", version="1.0.0",
        )
        self.ctx.metadata._set_spoof_name("evil")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="good", version="1.0.0",
            artifact_url=_pkg_url("good", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Mismatched-package edge cases (specs 24–25)
# ═══════════════════════════════════════════════════════════════════════


class TestMismatchedPackageEdgeCases(unittest.TestCase):
    """Every mismatch triggers a protected reinstall; presence alone
    is never treated as success."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_missing_package_triggers_install(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertGreater(self.ctx.download.call_count, 0)  # type: ignore[attr-defined]
        self.assertGreater(self.ctx.installer.call_count, 0)  # type: ignore[attr-defined]

    def test_wrong_package_name_triggers_reinstall(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="good", version="1.0.0",
        )
        self.ctx.metadata._set_spoof_name("evil")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="good", version="1.0.0",
            artifact_url=_pkg_url("good", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_wrong_version_triggers_reinstall(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="0.9.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertGreater(self.ctx.download.call_count, 0)  # type: ignore[attr-defined]
        self.assertGreater(self.ctx.installer.call_count, 0)  # type: ignore[attr-defined]
        self.assertFalse(result.ok)

    def test_malformed_package_json_yields_failure(self) -> None:
        self.ctx.metadata._set_malformed(True)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_metadata_path_is_directory(self) -> None:
        self.ctx.metadata._set_is_directory(True)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)

    def test_mismatch_policy_never_treats_presence_as_success(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="target", version="1.0.0",
        )
        self.ctx.metadata._set_spoof_name("other")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="target", version="1.0.0",
            artifact_url=_pkg_url("target", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)


class TestMetadataPreCheckErrorDiscrimination(unittest.TestCase):
    """Only :class:`MetadataNotFoundError` triggers a fresh install.
    Read/parse/permission failures surface immediately without download."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def _single_entry(self) -> ProjectionEntry:
        return ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"),
            artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )

    def test_metadata_not_found_triggers_install(self) -> None:
        """MetadataNotFoundError → download + install proceeds."""
        entries = [self._single_entry()]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertEqual(InstallStatus.OK, result.results[0].status)
        self.assertIn(
            "download",
            self.ctx.download._call_log,  # type: ignore[attr-defined]
        )

    def test_malformed_metadata_surfaces_without_install(self) -> None:
        """Parse/malformed error → surfaced as FAILED; no download."""
        self.ctx.metadata._malformed = True  # type: ignore[attr-defined]
        entries = [self._single_entry()]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)
        self.assertNotIn(
            "download",
            self.ctx.download._call_log,  # type: ignore[attr-defined]
            "malformed metadata must not trigger a download",
        )

    def test_read_failure_surfaces_without_install(self) -> None:
        """Generic InstallError (e.g. permission) → FAILED; no download."""
        self.ctx.metadata._fail_on_next_read(  # type: ignore[attr-defined]
            InstallError("EACCES: permission denied"),
        )
        entries = [self._single_entry()]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)
        self.assertNotIn(
            "download",
            self.ctx.download._call_log,  # type: ignore[attr-defined]
            "read permission error must not trigger a download",
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Reinstall + identity/version validation (specs 26–29)
# ═══════════════════════════════════════════════════════════════════════


class TestReinstallAndValidate(unittest.TestCase):
    """Successful reinstall followed by exact identity/version check."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_successful_reinstall_with_exact_match(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)

    def test_successful_install_missing_post_install_metadata(self) -> None:
        self.ctx.metadata._fail_on_all_reads(  # type: ignore[attr-defined]
            InstallError("package.json not found after install"),
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_successful_install_wrong_post_install_identity(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="genuine", version="1.0.0",
        )
        self.ctx.metadata._set_spoof_name("impostor")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="genuine", version="1.0.0",
            artifact_url=_pkg_url("genuine", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)

    def test_successful_install_wrong_post_install_version(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="0.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Multiple extensions (spec 30)
# ═══════════════════════════════════════════════════════════════════════


class TestMultipleExtensions(unittest.TestCase):
    """Multiple extensions: matches skipped, mismatches repaired,
    first failure stops subsequent mutations, prior successes reported."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_matching_entries_skipped(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="skip-me", version="1.0.0",
        )
        entries = [
            ProjectionEntry(
                package="skip-me", version="1.0.0",
                artifact_url=_pkg_url("skip-me", "1.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
            ProjectionEntry(
                package="install-me", version="2.0.0",
                artifact_url=_pkg_url("install-me", "2.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
        ]
        self.ctx.installer._expect_version("install-me", "2.0.0")  # type: ignore[attr-defined]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )
        self.assertEqual(
            InstallStatus.OK, result.results[1].status,
        )

    def test_mismatches_repaired(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="stale", version="0.9.0",
        )
        entries = [ProjectionEntry(
            package="stale", version="1.0.0",
            artifact_url=_pkg_url("stale", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertGreater(self.ctx.download.call_count, 0)  # type: ignore[attr-defined]

    def test_first_failure_stops_subsequent_mutations(self) -> None:
        self.ctx.download._fail_with(  # type: ignore[attr-defined]
            InstallError("network unreachable"),
        )
        entries = [
            ProjectionEntry(
                package="first", version="1.0.0",
                artifact_url=_pkg_url("first", "1.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
            ProjectionEntry(
                package="second", version="2.0.0",
                artifact_url=_pkg_url("second", "2.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
        ]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(1, self.ctx.download.call_count)  # type: ignore[attr-defined]

    def test_prior_successful_entries_accurately_reported(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="ok-pkg", version="1.0.0",
        )
        self.ctx.download._fail_after_n(0)  # type: ignore[attr-defined]
        entries = [
            ProjectionEntry(
                package="ok-pkg", version="1.0.0",
                artifact_url=_pkg_url("ok-pkg", "1.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
            ProjectionEntry(
                package="fail-pkg", version="2.0.0",
                artifact_url=_pkg_url("fail-pkg", "2.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
        ]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )
        self.assertEqual(
            InstallStatus.FAILED, result.results[1].status,
        )
        self.assertFalse(result.ok)


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Post-install identity/version validation
# ═══════════════════════════════════════════════════════════════════════


class TestPostInstallValidation(unittest.TestCase):
    """After installation, metadata must be verified against the projection."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_post_install_match_is_ok(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)

    def test_post_install_name_mismatch_is_failure(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="right", version="1.0.0",
        )
        self.ctx.metadata._set_spoof_name("evil")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="right", version="1.0.0",
            artifact_url=_pkg_url("right", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)


class TestAlreadyInstalledOwnerValidation(unittest.TestCase):
    """A matching name/version must NOT bypass ``validate_owner`` —
    root- or foreign-owned installed metadata must be rejected."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def _matching_entry(self) -> ProjectionEntry:
        return ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"),
            artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )

    def test_wrong_owner_is_reported_as_failed(self) -> None:
        """Name + version match, but owner is not dev:dev → FAILED."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        self.ctx.privilege._fail_validate = True  # type: ignore[attr-defined]
        entries = [self._matching_entry()]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertFalse(result.ok)
        self.assertEqual(InstallStatus.FAILED, result.results[0].status)

    def test_wrong_owner_calls_validate_owner(self) -> None:
        """validate_owner is invoked even for matching installed packages."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        self.ctx.privilege._fail_validate = True  # type: ignore[attr-defined]
        entries = [self._matching_entry()]
        install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertIn(
            "privilege.validate_owner",
            self.ctx.privilege._call_log,  # type: ignore[attr-defined]
            "validate_owner must be called even for ALREADY_INSTALLED",
        )

    def test_correct_owner_still_reports_already_installed(self) -> None:
        """Correct owner (dev:dev) with matching metadata → ALREADY_INSTALLED."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [self._matching_entry()]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )
        self.assertIn(
            "privilege.validate_owner",
            self.ctx.privilege._call_log,  # type: ignore[attr-defined]
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — metadata_file passthrough
# ═══════════════════════════════════════════════════════════════════════


def _npm_metadata_path(pi_home: str, package: str, metadata_file: str) -> str:
    """Resolve the installed metadata path in the Pi CLI npm layout."""
    import os
    return os.path.join(
        pi_home, "agent", "npm", "node_modules", package, metadata_file,
    )


class TestMetadataPathResolution(unittest.TestCase):
    """Installed metadata MUST resolve to the exact npm layout:
    ``<pi_home>/agent/npm/node_modules/<package>/<metadata_file>``.
    Unscoped, scoped, and nested metadata_file variants must all
    produce the correct path."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    # ── unscoped, default metadata_file ──────────────────────────

    def test_unscoped_default_metadata_path(self) -> None:
        entries = [ProjectionEntry(
            package="pi-read", version="1.0.0",
            artifact_url=_pkg_url("pi-read", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = "/mnt/pi/agent/npm/node_modules/pi-read/package.json"
        self._assert_validate_owner_called_for(expected)

    # ── unscoped, nested metadata_file ───────────────────────────

    def test_unscoped_nested_metadata_path(self) -> None:
        self.ctx.installer._expect_version("my-pkg", "2.0.0")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="my-pkg", version="2.0.0",
            artifact_url=_pkg_url("my-pkg", "2.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="dist/package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = "/mnt/pi/agent/npm/node_modules/my-pkg/dist/package.json"
        self._assert_validate_owner_called_for(expected)

    # ── scoped, default metadata_file ────────────────────────────

    def test_scoped_default_metadata_path(self) -> None:
        self.ctx.installer._expect_version("@earendil-works/pi", "3.0.0")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="@earendil-works/pi", version="3.0.0",
            artifact_url=_pkg_url("@earendil-works/pi", "3.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = (
            "/mnt/pi/agent/npm/node_modules/"
            "@earendil-works/pi/package.json"
        )
        self._assert_validate_owner_called_for(expected)

    # ── scoped, nested metadata_file ─────────────────────────────

    def test_scoped_nested_metadata_path(self) -> None:
        self.ctx.installer._expect_version("@scope/pkg", "2.0.0")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="@scope/pkg", version="2.0.0",
            artifact_url=_pkg_url("@scope/pkg", "2.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="sub/package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = (
            "/mnt/pi/agent/npm/node_modules/@scope/pkg/sub/package.json"
        )
        self._assert_validate_owner_called_for(expected)

    # ── different pi_home ────────────────────────────────────────

    def test_different_pi_home_changes_prefix(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/opt/pi-home",
        )
        expected = "/opt/pi-home/agent/npm/node_modules/p/package.json"
        self._assert_validate_owner_called_for(expected)

    # ── reject paths not inside the npm layout ───────────────────

    def test_rejects_path_outside_npm_layout(self) -> None:
        """A bare path like /mnt/pi/package.json is never valid."""
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        for path, _ in self.ctx.privilege._owner_validations:  # type: ignore[attr-defined]
            self.assertIn("/agent/npm/node_modules/", path,
                          "metadata path must be inside npm node_modules")

    # ── helpers ──────────────────────────────────────────────────

    def _assert_validate_owner_called_for(self, expected: str) -> None:
        changes = self.ctx.privilege._owner_validations  # type: ignore[attr-defined]
        self.assertGreater(len(changes), 0,
                           f"expected validate_owner({expected!r})")
        paths = [p for p, _ in changes]
        self.assertIn(expected, paths,
                      f"expected {expected!r} in validate_owner paths {paths!r}")


class TestMetadataFilePassthrough(unittest.TestCase):
    """The projected metadata_file is passed to every MetadataReader.read
    call (pre-check and post-install) and the resolved path is passed to
    PrivilegeContext.validate_owner.  Non-default nested paths must work
    end-to-end."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    # ── pre-check read receives metadata_file ────────────────────

    def test_pre_check_read_receives_default_metadata_file(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        first_read = self.ctx.metadata._last_read  # type: ignore[attr-defined]
        self.assertEqual("package.json", first_read["metadata_file"])
        self.assertEqual("p", first_read["package"])
        self.assertEqual("/mnt/pi", first_read["pi_home"])

    def test_pre_check_read_receives_nested_metadata_file(self) -> None:
        entries = [ProjectionEntry(
            package="@scope/pkg", version="3.2.1",
            artifact_url=_pkg_url("@scope/pkg", "3.2.1"), artifact_integrity=_VALID_SHA256,
            metadata_file="nested/deep/package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        first_read = self.ctx.metadata._last_read  # type: ignore[attr-defined]
        self.assertEqual("nested/deep/package.json",
                         first_read["metadata_file"])

    # ── post-install read receives the same metadata_file ────────

    def test_post_install_read_receives_metadata_file(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="sub/pkg.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertEqual(
            InstallStatus.ALREADY_INSTALLED, result.results[0].status,
        )
        self.assertEqual(
            "sub/pkg.json",
            self.ctx.metadata._last_read["metadata_file"],  # type: ignore[attr-defined]
        )

    # ── validate_owner receives resolved metadata path ─────────────

    def test_validate_owner_receives_resolved_default_path(self) -> None:
        """Unscoped package → /mnt/pi/agent/npm/node_modules/pkg/package.json."""
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = "/mnt/pi/agent/npm/node_modules/p/package.json"
        paths = [p for p, _ in self.ctx.privilege._owner_validations]  # type: ignore[attr-defined]
        self.assertIn(expected, paths,
                      f"expected {expected!r} in {paths!r}")

    def test_validate_owner_receives_resolved_nested_path(self) -> None:
        """Scoped package, nested metadata → full npm layout path."""
        self.ctx.installer._expect_version("@s/p", "2.0.0")  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="@s/p", version="2.0.0",
            artifact_url=_pkg_url("@s/p", "2.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="dist/pkg.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        expected = "/mnt/pi/agent/npm/node_modules/@s/p/dist/pkg.json"
        paths = [p for p, _ in self.ctx.privilege._owner_validations]  # type: ignore[attr-defined]
        self.assertIn(expected, paths,
                      f"expected {expected!r} in {paths!r}")

    # ── different entries carry different metadata_file ──────────

    def test_two_entries_different_metadata_files(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="a", version="1.0.0",
        )
        entries = [
            ProjectionEntry(
                package="a", version="1.0.0",
                artifact_url=_pkg_url("a", "1.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="a/package.json",
            ),
            ProjectionEntry(
                package="b", version="2.0.0",
                artifact_url=_pkg_url("b", "2.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="b/custom.json",
            ),
        ]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        # The fake records the *last* read; for "b" it should be b/custom.json
        last = self.ctx.metadata._last_read  # type: ignore[attr-defined]
        self.assertEqual("b/custom.json", last["metadata_file"])
        self.assertEqual("b", last["package"])


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Mount check guard
# ═══════════════════════════════════════════════════════════════════════


class TestPiHomeMountCheck(unittest.TestCase):
    """Installation refused when pi_home is not a mount point."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_not_mount_raises_install_error(self) -> None:
        self.ctx.mount_check._set_mount(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
            )

    def test_mount_failure_before_any_io(self) -> None:
        self.ctx.mount_check._set_mount(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        try:
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
            )
        except InstallError:
            pass
        self.assertEqual(0, self.ctx.download.call_count)  # type: ignore[attr-defined]
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    def test_is_mount_allows_proceeding(self) -> None:
        self.ctx.mount_check._set_mount(True)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi",
        )
        self.assertIsInstance(result, InstallResult)


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Dry-run
# ═══════════════════════════════════════════════════════════════════════


class TestDryRun(unittest.TestCase):
    """Dry-run reports what *would* happen without side-effects."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_dry_run_does_not_install(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        result = install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi", dry_run=True,
        )
        self.assertTrue(result.dry_run)
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    def test_dry_run_does_not_download(self) -> None:
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        install_extensions(
            self.ctx, entries=entries, pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(0, self.ctx.download.call_count)  # type: ignore[attr-defined]

    def test_dry_run_still_checks_mount(self) -> None:
        self.ctx.mount_check._set_mount(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
                dry_run=True,
            )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Pi-home safety (spec 31)
# ═══════════════════════════════════════════════════════════════════════


class TestPiHomeSafety(unittest.TestCase):
    """Pi-home must be a real, mounted, writable directory.
    Metadata must not resolve outside Pi home."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    def test_absent_pi_home_raises(self) -> None:
        self.ctx.mount_check._set_exists(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/nonexistent",
            )

    def test_pi_home_not_mounted_raises(self) -> None:
        self.ctx.mount_check._set_mount(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
            )

    def test_pi_home_is_symlink_raises(self) -> None:
        self.ctx.mount_check._set_is_symlink(True)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
            )

    def test_metadata_resolves_outside_pi_home_raises(self) -> None:
        with self.assertRaises(MetadataValidationError):
            ProjectionEntry(
                package="p", version="1.0.0",
                artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
                metadata_file="../../etc/passwd",
            )

    def test_non_writable_pi_home_raises(self) -> None:
        self.ctx.mount_check._set_writable(False)  # type: ignore[attr-defined]
        entries = [ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=entries, pi_home="/mnt/pi",
            )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Ownership expectations (spec 32)
# ═══════════════════════════════════════════════════════════════════════


class TestOwnershipExpectations(unittest.TestCase):
    """Installer enforces dev identity before mutation; ensures
    installed files are owned dev:dev; no ownership changes outside
    Pi home."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()
        self.p = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )

    # ── verify_user boundary ──────────────────────────────────────

    def test_verifies_running_as_dev_before_mutation(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi",
        )
        verified = self.ctx.privilege._verified_user  # type: ignore[attr-defined]
        self.assertEqual("dev", verified,
                         "must verify current user is dev before any mutation")

    def test_wrong_user_blocks_all_mutations(self) -> None:
        self.ctx.privilege._verified_user = None  # type: ignore[attr-defined]
        self.ctx.privilege._fail_verify = True     # type: ignore[attr-defined]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=[self.p], pi_home="/mnt/pi",
            )
        self.assertEqual(0, self.ctx.download.call_count)   # type: ignore[attr-defined]
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    # ── validate_owner boundary ─────────────────────────────────────

    def test_validates_owner_on_installed_metadata(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi",
        )
        changes = self.ctx.privilege._owner_validations  # type: ignore[attr-defined]
        self.assertGreater(len(changes), 0,
                           "must call validate_owner after install")

    def test_validates_dev_colon_dev_ownership(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi",
        )
        for _, owner in self.ctx.privilege._owner_validations:  # type: ignore[attr-defined]
            self.assertEqual("dev:dev", owner)

    def test_no_validations_outside_npm_layout(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi",
        )
        npm_prefix = "/mnt/pi/agent/npm/node_modules/"
        for path, _ in self.ctx.privilege._owner_validations:  # type: ignore[attr-defined]
            self.assertTrue(
                path.startswith(npm_prefix),
                f"validate_owner path {path!r} must be under {npm_prefix!r}",
            )

    def test_dry_run_skips_ownership_validation(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi",
            dry_run=True,
        )
        self.assertEqual(
            [], self.ctx.privilege._owner_validations,  # type: ignore[attr-defined]
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Dry-run contract (spec 33)
# ═══════════════════════════════════════════════════════════════════════


class TestDryRunContract(unittest.TestCase):
    """Dry-run: projection loaded + validated, metadata inspected
    read-only, planned operations reported, no mutation."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()
        self.p = ProjectionEntry(
            package="p", version="1.0.0",
            artifact_url=_pkg_url("p", "1.0.0"), artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )

    def test_dry_run_loads_and_validates_projection(self) -> None:
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertTrue(result.dry_run)
        self.assertIsInstance(result, InstallResult)

    def test_dry_run_inspects_metadata_read_only(self) -> None:
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertGreater(self.ctx.metadata.call_count, 0)  # type: ignore[attr-defined]

    def test_dry_run_reports_planned_downloads(self) -> None:
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertTrue(result.dry_run)

    def test_dry_run_no_network(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(0, self.ctx.download.call_count)  # type: ignore[attr-defined]

    def test_dry_run_no_package_execution(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    def test_dry_run_no_filesystem_mutation(self) -> None:
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(0, self.ctx.installer.call_count)  # type: ignore[attr-defined]

    def test_dry_run_absent_package_no_ownership_check(self) -> None:
        """When the package is not installed, ownership is never checked."""
        install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(
            [], self.ctx.privilege._owner_validations,  # type: ignore[attr-defined]
        )

    def test_dry_run_matching_package_validates_ownership(self) -> None:
        """Dry-run with a matching installed package MUST validate ownership."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="1.0.0",
        )
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(InstallStatus.ALREADY_INSTALLED, result.results[0].status)
        self.assertIn(
            "privilege.validate_owner",
            self.ctx.privilege._call_log,  # type: ignore[attr-defined]
            "dry-run must validate ownership for ALREADY_INSTALLED",
        )

    def test_dry_run_absent_package_reports_planned(self) -> None:
        """Package not installed → PLANNED, not ALREADY_INSTALLED."""
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertTrue(result.dry_run)
        self.assertEqual(InstallStatus.PLANNED, result.results[0].status)

    def test_dry_run_mismatched_version_reports_planned(self) -> None:
        """Installed version differs from projected → PLANNED (reinstall)."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="p", version="0.9.0",
        )
        result = install_extensions(
            self.ctx, entries=[self.p], pi_home="/mnt/pi", dry_run=True,
        )
        self.assertEqual(InstallStatus.PLANNED, result.results[0].status)

    def test_dry_run_malformed_metadata_surfaces_error(self) -> None:
        """Malformed installed metadata → raise, do not swallow."""
        self.ctx.metadata._malformed = True  # type: ignore[attr-defined]
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=[self.p], pi_home="/mnt/pi",
                dry_run=True,
            )

    def test_dry_run_permission_failure_surfaces_error(self) -> None:
        """Read permission failure → raise, do not swallow."""
        self.ctx.metadata._fail_on_next_read(  # type: ignore[attr-defined]
            InstallError("EACCES: permission denied"),
        )
        with self.assertRaises(InstallError):
            install_extensions(
                self.ctx, entries=[self.p], pi_home="/mnt/pi",
                dry_run=True,
            )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 cont. — Source contract (spec 34)
# ═══════════════════════════════════════════════════════════════════════


class TestSourceContract(unittest.TestCase):
    """Installer references only the runtime projection; never reads
    reviewed inventory, build projection, update providers, or
    override policy."""

    def test_install_extensions_receives_only_projection_entries(self) -> None:
        sig = inspect.signature(install_extensions)
        param_names = set(sig.parameters.keys())
        allowed = {"ctx", "entries", "pi_home", "dry_run"}
        self.assertEqual(
            param_names - {"args", "kwargs"},
            allowed,
            "install_extensions must only accept ctx, entries, pi_home, dry_run",
        )

    def test_read_projection_only_needs_path(self) -> None:
        sig = inspect.signature(read_projection)
        param_names = set(sig.parameters.keys())
        self.assertEqual(
            {"path"},
            param_names - {"args", "kwargs"},
            "read_projection must only accept a path",
        )

    def test_module_does_not_import_inventory(self) -> None:
        import ast
        mod_path = os.path.join(
            os.path.dirname(__file__), "..", "docker",
            "runtime_installer.py",
        )
        with open(mod_path) as fh:
            tree = ast.parse(fh.read())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        forbidden = {
            "docker.versioning.inventory",
            "docker.versioning.effective",
            "docker.versioning.updates",
            "docker.versioning.model",
            "docker.versions",
        }
        intersection = imports & forbidden
        self.assertEqual(
            set(), intersection,
            f"runtime_installer must not import {sorted(intersection)}",
        )
        # The shared npm_tarball and semver modules are the only
        # allowed versioning imports — they are focused,
        # dependency-free validators used by both model and
        # installer.
        for mod in ("docker.versioning.npm_tarball",
                     "docker.versioning.semver"):
            self.assertIn(
                mod, imports,
                f"runtime_installer must import the shared {mod} validator",
            )

    def test_installer_never_receives_inventory_path(self) -> None:
        fields = {f.name for f in ProjectionEntry.__dataclass_fields__.values()}
        self.assertNotIn("inventory_path", fields)
        self.assertNotIn("build_projection_path", fields)
        self.assertNotIn("source", fields)
        self.assertNotIn("update", fields)
        self.assertNotIn("override", fields)

    def test_entrypoint_invokes_protected_installer_not_wrapper(self) -> None:
        entrypoint = os.path.join(
            os.path.dirname(__file__), "..", "docker", "entrypoint.sh",
        )
        with open(entrypoint) as fh:
            content = fh.read()
        self.assertIn(
            "python3 -m docker.runtime_installer install", content,
            "entrypoint must invoke the protected Python installer, "
            "not a legacy shell wrapper",
        )

    def test_dockerfile_copies_installer_module_not_wrapper(self) -> None:
        dockerfile = os.path.join(
            os.path.dirname(__file__), "..", "Dockerfile",
        )
        with open(dockerfile) as fh:
            content = fh.read()
        self.assertIn(
            "COPY docker/runtime_installer.py", content,
            "Dockerfile must copy the protected Python installer",
        )
        self.assertNotIn(
            "COPY docker/install-pi-extensions.sh", content,
            "Dockerfile must NOT copy the legacy shell wrapper",
        )

    def test_dockerfile_entrypoint_is_sole_startup_path(self) -> None:
        dockerfile = os.path.join(
            os.path.dirname(__file__), "..", "Dockerfile",
        )
        with open(dockerfile) as fh:
            content = fh.read()
        self.assertIn(
            'ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]',
            content,
            "Dockerfile must define the entrypoint as the sole startup path",
        )
        # The entrypoint is the only supported runtime extension-installation
        # path; no other scripts should be copied as startup surface.
        self.assertNotIn(
            "COPY docker/install-pi-extensions.sh", content,
            "Dockerfile must NOT copy the obsolete shell wrapper",
        )


# ═══════════════════════════════════════════════════════════════════════
# 10.2 — Exit codes
# ═══════════════════════════════════════════════════════════════════════


class TestExitCodeMapping(unittest.TestCase):
    """exit_code_for maps structured outcomes to shell exit codes."""

    def test_ok_to_zero(self) -> None:
        result = InstallResult(results=(
            ExtensionResult(package="p", version="1", status=InstallStatus.OK),
        ))
        self.assertEqual(0, exit_code_for(result))

    def test_already_installed_to_zero(self) -> None:
        result = InstallResult(results=(
            ExtensionResult(
                package="p", version="1",
                status=InstallStatus.ALREADY_INSTALLED,
            ),
        ))
        self.assertEqual(0, exit_code_for(result))

    def test_failed_to_nonzero(self) -> None:
        result = InstallResult(results=(
            ExtensionResult(
                package="p", version="1",
                status=InstallStatus.FAILED, detail="boom",
            ),
        ))
        self.assertNotEqual(0, exit_code_for(result))

    def test_install_error_to_nonzero(self) -> None:
        self.assertNotEqual(0, exit_code_for(InstallError("mount")))


# ═══════════════════════════════════════════════════════════════════════
# Fake boundary implementations
# ═══════════════════════════════════════════════════════════════════════



def _pkg_url(package: str, version: str) -> str:
    """Valid npm tarball URL for the given package and version.

    Npm tarball filenames never include ``+build`` metadata — the
    model strips it.  This helper mirrors that contract."""
    basename = package.split("/")[-1]
    base_ver = version.split("+", 1)[0]
    return f"https://registry.npmjs.org/{package}/-/{basename}-{base_ver}.tgz"


_dummy_bytes = b"a"  # matches _VALID_SHA256


class _CallRecorder:
    """Mixin that records every method call in ``_call_log``."""

    def __init__(self) -> None:
        self._call_log: list[str] = []


class _FakeMountChecker(_CallRecorder, MountChecker):
    def __init__(self) -> None:
        _CallRecorder.__init__(self)
        self._is_mount = True
        self._exists = True
        self._is_symlink = False
        self._metadata_outside = False
        self._writable = True
        self.call_count = 0

    def is_mount(self, path: str) -> bool:
        self._call_log.append("mount_check")
        self.call_count += 1
        if not self._exists:
            raise InstallError(f"{path}: does not exist")
        if self._is_symlink:
            raise InstallError(f"{path}: is a symlink")
        if not self._writable:
            raise InstallError(f"{path}: not writable")
        return self._is_mount

    def _set_mount(self, value: bool) -> None:
        self._is_mount = value

    def _set_exists(self, value: bool) -> None:
        self._exists = value

    def _set_is_symlink(self, value: bool) -> None:
        self._is_symlink = value

    def _set_metadata_outside(self, value: bool) -> None:
        self._metadata_outside = value

    def _set_writable(self, value: bool) -> None:
        self._writable = value


class _FakeArtifactDownloader(_CallRecorder, ArtifactDownloader):
    """Returns a local path — never verifies or returns bytes."""

    def __init__(self, fs: "_FakeArtifactFilesystem | None" = None) -> None:
        _CallRecorder.__init__(self)
        self._failure: BaseException | None = None
        self._fail_after: int | None = None
        self._fs = fs
        self.call_count = 0
        self._last_call: dict[str, object] = {}

    def fetch(self, *, url: str, dest_dir: str) -> str:
        self._call_log.append("download")
        self.call_count += 1
        self._last_call = {"url": url, "dest_dir": dest_dir}
        if self._fail_after is not None and self.call_count > self._fail_after:
            raise (self._failure or InstallError("download failed after N"))
        if self._failure:
            raise self._failure
        artifact_path = f"{dest_dir}/artifact.tgz"
        if self._fs is not None:
            self._fs._register_file(artifact_path)
        return artifact_path

    def _fail_with(self, exc: BaseException) -> None:
        """Raise *exc* on the next (or every) :meth:`fetch` call."""
        self._failure = exc

    def _fail_after_n(self, n: int) -> None:
        self._fail_after = n


class _FakeArtifactFilesystem(_CallRecorder, ArtifactFilesystem):
    """Holds bytes in memory keyed by path; tracks removals;
    provides fake stat/realpath/absolute operations."""

    def __init__(self) -> None:
        _CallRecorder.__init__(self)
        self._bytes: dict[str, bytes] = {}
        self._default_bytes: bytes = _dummy_bytes
        self._removed: set[str] = set()
        self._fail_read: bool = False
        self._fail_remove: bool = False
        self.call_count = 0
        self._last_read_path: str | None = None
        # path → (st_mode, realpath_result)
        self._stat_map: dict[str, tuple[int, str]] = {}

    # ── new protocol methods ────────────────────────────────────

    def is_absolute(self, path: str) -> bool:
        return path.startswith("/")

    def lstat_mode(self, path: str) -> int:
        self._call_log.append("file.lstat_mode")
        try:
            return self._stat_map[path][0]
        except KeyError:
            raise FileNotFoundError(f"fake: no entry for {path!r}")

    def realpath(self, path: str) -> str:
        self._call_log.append("file.realpath")
        try:
            return self._stat_map[path][1]
        except KeyError:
            return path  # workspace_dir etc.

    def _register_file(
        self, path: str, *, realpath: str | None = None,
    ) -> None:
        """Register a regular file entry at *path*."""
        import stat
        self._stat_map[path] = (
            stat.S_IFREG | 0o644,
            realpath if realpath is not None else path,
        )

    def _register_symlink(self, path: str, *, real_target: str) -> None:
        """Register a symlink entry at *path*."""
        import stat
        self._stat_map[path] = (
            stat.S_IFLNK | 0o777,
            real_target,
        )

    # ── existing methods ────────────────────────────────────────

    def read_bytes(self, path: str) -> bytes:
        self._call_log.append("file.read_bytes")
        self.call_count += 1
        self._last_read_path = path
        if self._fail_read:
            raise InstallError(f"cannot read {path}")
        return self._bytes.get(path, self._default_bytes)

    def remove(self, path: str) -> None:
        self._call_log.append("file.remove")
        if self._fail_remove:
            raise InstallError(f"cannot remove {path}")
        self._removed.add(path)

    def _set_bytes(self, value: bytes) -> None:
        """Bytes returned by read_bytes for any path (via _default_bytes)."""
        self._default_bytes = value


class _FakeTempWorkspace(_CallRecorder, TempWorkspace):
    """Creates unique workspace paths and tracks cleanups."""

    def __init__(self) -> None:
        _CallRecorder.__init__(self)
        self._counter = 0
        self._created: list[str] = []
        self._cleaned: set[str] = set()
        self._fail_create: bool = False
        call_count = 0  # noqa: F841

    def create(self) -> str:
        self._call_log.append("workspace.create")
        if self._fail_create:
            raise InstallError("cannot create temp workspace")
        self._counter += 1
        path = f"/tmp/pi-install-{self._counter:04d}"
        self._created.append(path)
        return path

    def cleanup(self, path: str) -> None:
        self._call_log.append("workspace.cleanup")
        self._cleaned.add(path)


class _FakePackageInstaller(_CallRecorder, PackageInstaller):
    """Receives only verified artifact paths — never constructs URLs."""

    def __init__(self, metadata: "_FakeMetadataReader | None" = None) -> None:
        _CallRecorder.__init__(self)
        self._failure: BaseException | None = None
        self._metadata = metadata
        self._expected_versions: dict[str, str] = {}
        self.call_count = 0
        self._last_call: dict[str, object] = {}

    def install(self, *, package: str, artifact_bytes: bytes) -> None:
        self._call_log.append("install")
        self.call_count += 1
        self._last_call = {"package": package, "artifact_bytes_len": len(artifact_bytes)}
        if self._failure:
            raise self._failure
        if self._metadata is not None and package not in self._metadata._installed:
            # Simulate fresh install: metadata becomes readable.
            version = self._expected_versions.get(package, "1.0.0")
            self._metadata._installed[package] = {"name": package, "version": version}

    def _fail_with(self, exc: InstallError) -> None:
        self._failure = exc

    def _expect_version(self, package: str, version: str) -> None:
        self._expected_versions[package] = version


class _FakeMetadataReader(_CallRecorder, MetadataReader):
    def __init__(self) -> None:
        _CallRecorder.__init__(self)
        self._installed: dict[str, dict[str, object]] = {}
        self._next_read_failure: InstallError | None = None
        self._keep_failing: bool = False
        self._spoof_name: str | None = None
        self._malformed = False
        self._is_directory = False
        self.call_count = 0

    def read(self, *, pi_home: str, metadata_file: str, package: str) -> dict[str, object]:
        self._call_log.append("metadata.read")
        self.call_count += 1
        self._last_read: dict[str, str] = {
            "pi_home": pi_home,
            "metadata_file": metadata_file,
            "package": package,
        }
        if self._next_read_failure:
            exc = self._next_read_failure
            if not self._keep_failing:
                self._next_read_failure = None
            raise exc
        if self._malformed:
            raise InstallError(f"{package}: malformed package.json")
        if self._is_directory:
            raise InstallError(
                f"{package}: metadata path is a directory",
            )
        if package in self._installed:
            result = dict(self._installed[package])
            if self._spoof_name is not None:
                result["name"] = self._spoof_name
            return result
        raise MetadataNotFoundError(f"{package}: not installed")

    def _set_installed(self, *, package: str, version: str) -> None:
        self._installed[package] = {"name": package, "version": version}

    def _fail_on_next_read(self, exc: InstallError) -> None:
        self._next_read_failure = exc

    def _fail_on_all_reads(self, exc: InstallError) -> None:
        """Repeatedly fail every read until cleared."""
        self._next_read_failure = exc
        self._keep_failing = True

    def _set_spoof_name(self, name: str) -> None:
        """Make reads for ANY package return this name (simulates
        a corrupt package.json with the wrong identity)."""
        self._spoof_name = name

    def _set_malformed(self, value: bool) -> None:
        self._malformed = value

    def _set_is_directory(self, value: bool) -> None:
        self._is_directory = value


class _FakePrivilegeContext(_CallRecorder, PrivilegeContext):
    def __init__(self) -> None:
        _CallRecorder.__init__(self)
        self._verified_user: str | None = None
        self._fail_verify: bool = False
        self._owner_validations: list[tuple[str, str]] = []
        self._fail_validate: bool = False

    def verify_user(self, expected: str) -> None:
        self._call_log.append("privilege.verify_user")
        if self._fail_verify:
            raise InstallError(f"not running as {expected}")
        self._verified_user = expected

    def validate_owner(self, path: str, owner: str) -> None:
        self._call_log.append("privilege.validate_owner")
        if self._fail_validate:
            raise InstallError(f"ownership validation failed: expected {owner} for {path}")
        self._owner_validations.append((path, owner))

    call_count = 0  # unused; _CallRecorder._call_log covers it


class _FakeInstallContext(InstallContext):
    """InstallContext whose fakes expose internal state for assertions."""

    def __init__(
        self,
        mount_check: _FakeMountChecker,
        workspace: _FakeTempWorkspace,
        download: _FakeArtifactDownloader,
        file: _FakeArtifactFilesystem,
        installer: _FakePackageInstaller,
        metadata: _FakeMetadataReader,
        privilege: _FakePrivilegeContext,
    ) -> None:
        object.__setattr__(self, "mount_check", mount_check)
        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(self, "download", download)
        object.__setattr__(self, "file", file)
        object.__setattr__(self, "installer", installer)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "privilege", privilege)
        self._call_log: list[str] = []


def _make_fake_context() -> _FakeInstallContext:
    meta = _FakeMetadataReader()
    fs = _FakeArtifactFilesystem()
    ctx = _FakeInstallContext(
        mount_check=_FakeMountChecker(),
        workspace=_FakeTempWorkspace(),
        download=_FakeArtifactDownloader(fs=fs),
        file=fs,
        installer=_FakePackageInstaller(metadata=meta),
        metadata=meta,
        privilege=_FakePrivilegeContext(),
    )
    # Share single call log across all fakes and the context.
    shared = ctx._call_log
    for attr in ("mount_check", "workspace", "download", "file",
                 "installer", "metadata", "privilege"):
        obj = getattr(ctx, attr)
        if hasattr(obj, "_call_log"):
            obj._call_log = shared
    return ctx


def _tmp_toml(content: str) -> str:
    import tempfile
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".toml", delete=False,
    )
    try:
        tmp.write(content)
    finally:
        tmp.close()
    return tmp.name


# ═══════════════════════════════════════════════════════════════════════
# 10.3 — Interruption coverage: KeyboardInterrupt / SystemExit
# ═══════════════════════════════════════════════════════════════════════


class TestWorkspaceCleanupOnInterruption(unittest.TestCase):
    """Workspace cleanup must execute on all exit paths, including
    :class:`KeyboardInterrupt` and :class:`SystemExit`."""

    def setUp(self) -> None:
        self.ctx = _make_fake_context()

    # ── helpers ──────────────────────────────────────────────────

    def _entries(self, *, package: str = "p", version: str = "1.0.0") -> list[ProjectionEntry]:
        return [ProjectionEntry(
            package=package, version=version,
            artifact_url=_pkg_url(package, version),
            artifact_integrity=_VALID_SHA256,
            metadata_file="package.json",
        )]

    # ── KeyboardInterrupt ────────────────────────────────────────

    def test_keyboard_interrupt_cleans_workspace(self) -> None:
        """KeyboardInterrupt during download → workspace cleanup invoked."""
        self.ctx.download._fail_with(KeyboardInterrupt())  # type: ignore[attr-defined]
        entries = self._entries()
        with self.assertRaises(KeyboardInterrupt):
            install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertIn(
            "workspace.cleanup",
            self.ctx.workspace._call_log,  # type: ignore[attr-defined]
            "workspace must be cleaned up on KeyboardInterrupt",
        )

    def test_keyboard_interrupt_during_download_cleans_artifact(self) -> None:
        """KeyboardInterrupt during install → artifact file removed.

        The download succeeds (artifact file is created), but a
        :class:`KeyboardInterrupt` fires during installation
        — the per-entry ``try/finally`` must still remove the
        downloaded artifact."""
        self.ctx.installer._fail_with(KeyboardInterrupt())  # type: ignore[attr-defined]
        entries = self._entries()
        with self.assertRaises(KeyboardInterrupt):
            install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertIn(
            "file.remove",
            self.ctx.file._call_log,  # type: ignore[attr-defined]
            "downloaded artifact must be removed on KeyboardInterrupt",
        )

    def test_keyboard_interrupt_still_cleans_workspace_for_already_installed(self) -> None:
        """KeyboardInterrupt after first entry ALREADY_INSTALLED → workspace cleaned."""
        self.ctx.metadata._set_installed(  # type: ignore[attr-defined]
            package="skip-me", version="1.0.0",
        )
        # Second entry triggers KeyboardInterrupt on download
        self.ctx.download._fail_with(KeyboardInterrupt())  # type: ignore[attr-defined]
        entries = [
            ProjectionEntry(
                package="skip-me", version="1.0.0",
                artifact_url=_pkg_url("skip-me", "1.0.0"),
                artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
            ProjectionEntry(
                package="will-interrupt", version="1.0.0",
                artifact_url=_pkg_url("will-interrupt", "1.0.0"),
                artifact_integrity=_VALID_SHA256,
                metadata_file="package.json",
            ),
        ]
        with self.assertRaises(KeyboardInterrupt):
            install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertIn(
            "workspace.cleanup",
            self.ctx.workspace._call_log,  # type: ignore[attr-defined]
        )

    # ── SystemExit ───────────────────────────────────────────────

    def test_system_exit_cleans_workspace(self) -> None:
        """SystemExit during download → workspace cleanup invoked."""
        self.ctx.download._fail_with(SystemExit(42))  # type: ignore[attr-defined]
        entries = self._entries()
        with self.assertRaises(SystemExit) as ctx:
            install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertEqual(ctx.exception.code, 42)
        self.assertIn(
            "workspace.cleanup",
            self.ctx.workspace._call_log,  # type: ignore[attr-defined]
            "workspace must be cleaned up on SystemExit",
        )

    def test_system_exit_cleans_artifact(self) -> None:
        """SystemExit during install → artifact file removed.

        Download succeeds, SystemExit fires during installation
        — per-entry ``try/finally`` must still remove the artifact."""
        self.ctx.installer._fail_with(SystemExit(1))  # type: ignore[attr-defined]
        entries = self._entries()
        with self.assertRaises(SystemExit):
            install_extensions(self.ctx, entries=entries, pi_home="/mnt/pi")
        self.assertIn(
            "file.remove",
            self.ctx.file._call_log,  # type: ignore[attr-defined]
            "downloaded artifact must be removed on SystemExit",
        )


# ═══════════════════════════════════════════════════════════════════
# Real-installer boundary — partial-write resilience
# ═══════════════════════════════════════════════════════════════════


class TestRealPackageInstallerPartialWrite(unittest.TestCase):
    """The real installer writes to a temp file via os.write,
    which may return after writing only part of the buffer.
    The installer must loop until all bytes are written, and the
    bytes passed to ``pi install`` must be exactly the original
    artifact bytes."""

    def setUp(self) -> None:
        # Always use the real installer (not a test double).
        self._installer = InstallContext.real_installer()

    def test_partial_writes_do_not_truncate_temp_file(self) -> None:
        """Simulate os.write returning partial counts (1 byte at a
        time), then verify that the file passed to ``pi install``
        contains exactly the original artifact bytes."""
        import subprocess

        artifact = b"\x00\x01\x02\x03" * 4096  # 16 KiB

        # Capture the path and verify written content from within
        # the mocked subprocess.run.
        captured: dict[str, bytes] = {}

        real_run = subprocess.run

        def _fake_run(cmd, **_kw):
            # cmd is ["pi", "install", <tmp_path>]
            tmp_path = cmd[2]
            with open(tmp_path, "rb") as fh:
                captured["written"] = fh.read()
            captured["cmd"] = cmd
            return real_run(
                ["true"], capture_output=True, text=True,
            )

        original_write = os.write
        write_count = {"calls": 0}

        def _partial_write(fd, data):
            write_count["calls"] += 1
            # Write at most 1 byte per call to force the loop.
            chunk = data[:1]
            return original_write(fd, chunk)

        with mock.patch("os.write", side_effect=_partial_write):
            with mock.patch(
                "subprocess.run", side_effect=_fake_run,
            ):
                self._installer.install("test-pkg", artifact)

        # Assertions
        self.assertEqual(
            captured.get("written"), artifact,
            "bytes written to temp file must equal original artifact bytes",
        )
        self.assertEqual(
            captured["cmd"][:2], ["pi", "install"],
            "subprocess must invoke pi install",
        )
        self.assertTrue(
            write_count["calls"] > 1,
            f"partial write must trigger multiple os.write calls, "
            f"got {write_count['calls']}",
        )

    def test_empty_artifact_completes_without_write(self) -> None:
        """Empty artifact bytes is a valid edge-case — the
        installer must handle it and pass an empty temp file to
        ``pi install``."""
        import subprocess

        captured: dict[str, bytes] = {}
        real_run = subprocess.run

        def _fake_run(cmd, **_kw):
            tmp_path = cmd[2]
            with open(tmp_path, "rb") as fh:
                captured["written"] = fh.read()
            return real_run(
                ["true"], capture_output=True, text=True,
            )

        with mock.patch("subprocess.run", side_effect=_fake_run):
            self._installer.install("empty-pkg", b"")

        self.assertEqual(
            captured.get("written"), b"",
            "empty artifact must produce empty temp file",
        )

    def test_subprocess_failure_propagates_install_error(self) -> None:
        """When pi install exits non-zero, the installer must
        raise InstallError and clean up the temp file."""
        artifact = b"payload"
        tmp_path_seen: list[str] = []

        def _fake_run(cmd, **_kw):
            tmp_path_seen.append(cmd[2])
            return mock.MagicMock(
                returncode=1, stderr="simulated failure",
            )

        with mock.patch("subprocess.run", side_effect=_fake_run):
            with self.assertRaises(InstallError) as ctx:
                self._installer.install("bad-pkg", artifact)
            self.assertIn("simulated failure", str(ctx.exception))

        # Temp file must be removed after failure.
        if tmp_path_seen:
            self.assertFalse(
                os.path.exists(tmp_path_seen[0]),
                "temp file must be cleaned up after install failure",
            )

    def test_os_write_zero_raises_oserror(self) -> None:
        """os.write returning 0 must raise OSError — a zero-length
        write would not advance the buffer, causing an infinite loop."""
        import subprocess

        artifact = b"some bytes"
        write_calls = 0
        original_write = os.write

        def _zero_then_ok(fd, data):
            nonlocal write_calls
            write_calls += 1
            if write_calls == 1:
                return 0  # simulate stalled write
            return original_write(fd, data)

        def _fake_run(cmd, **_kw):
            return subprocess.run(
                ["true"], capture_output=True, text=True,
            )

        with mock.patch("os.write", side_effect=_zero_then_ok):
            with mock.patch("subprocess.run", side_effect=_fake_run):
                with self.assertRaises(OSError) as ctx:
                    self._installer.install("pkg", artifact)
                self.assertIn("os.write returned 0", str(ctx.exception))

        self.assertEqual(
            write_calls, 1,
            "installer must not call os.write again after zero return",
        )


class TestArchitectureHostURLBoundary(unittest.TestCase):
    """RED — runtime URLs must be host-only; the container projection and
    installer must not expose or depend on downloadable URLs or download-
    transport/workspace production boundaries."""

    def test_projection_dto_has_no_url_field(self) -> None:
        from docker.runtime_installer import ProjectionEntry
        annotations = getattr(ProjectionEntry, "__annotations__", {})
        self.assertNotIn(
            "artifact_url", annotations,
            "ProjectionEntry must not expose artifact_url; URLs are host-only",
        )

    def test_projection_dto_has_canonical_identity_field(self) -> None:
        from docker.runtime_installer import ProjectionEntry
        annotations = getattr(ProjectionEntry, "__annotations__", {})
        self.assertIn(
            "artifact_id", annotations,
            "ProjectionEntry must carry a canonical artifact identity "
            "(not a downloadable URL)",
        )

    def test_installer_source_has_no_download_transport_imports(self) -> None:
        """The container installer source must never import urllib,
        requests, http.client, socket, or curl — whether top-level
        or inside a function body.

        Checking only ``vars(module)`` misses ``from X import Y``
        inside a function (the name is local, not module-level).
        This test scans the actual source text for import
        statements that reference forbidden download-transport
        modules."""
        import re

        import docker.runtime_installer
        src = inspect.getsource(docker.runtime_installer)
        forbidden = re.compile(
            r"^\s*(?:from|import)\s+"
            r"(?:urllib|requests|http\.client|socket|curl)"
            r"(?:\b|\s)",
            re.MULTILINE,
        )
        violations = [
            m.group(0).strip()
            for m in forbidden.finditer(src)
        ]
        self.assertEqual(
            [], violations,
            "installer source imports forbidden download transport:\n"
            + "\n".join(f"  {v}" for v in violations),
        )

    def test_installer_has_no_artifact_downloader_boundary(self) -> None:
        import docker.runtime_installer as mod
        self.assertFalse(
            hasattr(mod, "ArtifactDownloader"),
            "ArtifactDownloader protocol must not exist — the container "
            "receives pre-materialized read-only mounts",
        )

    def test_installer_has_no_temp_workspace_boundary(self) -> None:
        import docker.runtime_installer as mod
        self.assertFalse(
            hasattr(mod, "TempWorkspace"),
            "TempWorkspace must not exist — no mutable download workspace "
            "inside the container",
        )

    def test_installer_has_no_download_factory_function(self) -> None:
        import docker.runtime_installer as mod
        self.assertFalse(
            hasattr(mod, "real_workspace"),
            "real_workspace factory must not exist in the production module",
        )
        self.assertFalse(
            hasattr(mod, "real_download"),
            "real_download factory must not exist in the production module",
        )


if __name__ == "__main__":
    unittest.main()
