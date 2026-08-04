"""Stage 5.2 — Closed-DTO tests for EffectiveRuntimeProjection."""

import io
import unittest

from docker.versioning.model import (
    EffectivePiExtensionEntry,
    EffectiveRuntimeProjection,
    NpmArtifact,
)


class TestClosedRuntimeDTO(unittest.TestCase):
    """EffectiveRuntimeProjection is a closed DTO: its dataclass-generated
    __init__ already rejects unknown fields.  These tests verify structural
    guarantees and the post-init URL validation."""

    _INTEGRITY = (
        "sha512-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    )

    # ── helpers ──────────────────────────────────────────────────────

    def _artifact(self, url=None):
        if url is None:
            url = "https://registry.npmjs.org/p/-/p-1.0.0.tgz"
        return NpmArtifact(url=url, integrity=self._INTEGRITY)

    def _entry(self, **kw):
        defaults = {
            "package": "p",
            "version": "1.0.0",
            "artifact": self._artifact(),
            "metadata_file": "package.json",
        }
        defaults.update(kw)
        return EffectivePiExtensionEntry(**defaults)

    def _proj(self, **kw):
        defaults = {"extensions": {"p": self._entry()}}
        defaults.update(kw)
        return EffectiveRuntimeProjection(**defaults)

    # ── happy path ───────────────────────────────────────────────────

    def test_extensions_immutable_after_construction(self):
        p = self._proj()
        with self.assertRaises(TypeError):
            p.extensions["p"] = p.extensions["p"]  # type: ignore[index]

    # ── reject unknown fields (Python dataclass enforcement) ──────────

    def test_rejects_unknown_top_level_field(self):
        with self.assertRaises(TypeError) as ctx:
            EffectiveRuntimeProjection(extensions={}, foobar=True)  # type: ignore[call-arg]
        self.assertIn("foobar", str(ctx.exception))

    def test_rejects_unknown_extension_field(self):
        with self.assertRaises(TypeError) as ctx:
            EffectivePiExtensionEntry(
                package="p", version="1.0.0",
                artifact=self._artifact(),
                metadata_file="package.json",
                foobar=42,  # type: ignore[call-arg]
            )
        self.assertIn("foobar", str(ctx.exception))

    # ── reject build / update / override / source fields via dataclass ──

    def test_rejects_stages_field(self):
        with self.assertRaises(TypeError) as ctx:
            EffectiveRuntimeProjection(extensions={}, stages={})  # type: ignore[call-arg]
        self.assertIn("stages", str(ctx.exception))

    def test_rejects_source_field_on_entry(self):
        with self.assertRaises(TypeError):
            self._entry(source=None)  # type: ignore[call-arg]

    def test_rejects_update_field_on_entry(self):
        with self.assertRaises(TypeError):
            self._entry(update=None)  # type: ignore[call-arg]

    def test_rejects_override_field_on_entry(self):
        with self.assertRaises(TypeError):
            self._entry(override=None)  # type: ignore[call-arg]

    def test_rejects_validation_field_on_entry(self):
        with self.assertRaises(TypeError):
            self._entry(validation=None)  # type: ignore[call-arg]

    def test_rejects_artifacts_field_on_entry(self):
        with self.assertRaises(TypeError):
            self._entry(artifacts=None)  # type: ignore[call-arg]

    # ── URL validation in __post_init__ ──────────────────────────────

    def test_url_fragment_rejected_in_post_init(self):
        with self.assertRaises(ValueError) as ctx:
            self._entry(
                artifact=self._artifact(
                    "https://registry.npmjs.org/p/-/p-1.0.0.tgz#1.0.0"
                )
            )
        self.assertIn("query/fragment", str(ctx.exception).lower())

    def test_wrong_tarball_name_rejected_in_post_init(self):
        with self.assertRaises(ValueError) as ctx:
            self._entry(
                artifact=self._artifact(
                    "https://registry.npmjs.org/p/-/wrong-1.0.0.tgz"
                )
            )
        self.assertIn("expected tarball", str(ctx.exception).lower())

    # ── round-trip through plain dict → reconstruction ───────────────

    def test_round_trip_preserves_all_fields(self):
        p = self._proj()
        ext = p.extensions["p"]
        self.assertEqual(ext.package, "p")
        self.assertEqual(ext.version, "1.0.0")
        self.assertEqual(ext.artifact.url, "https://registry.npmjs.org/p/-/p-1.0.0.tgz")
        self.assertEqual(ext.artifact.integrity, self._INTEGRITY)
        self.assertEqual(ext.metadata_file, "package.json")


# ═══════════════════════════════════════════════════════════════════════
# Task 4.1 — Replace downloadable URL with canonical mounted-artifact identity
# ═══════════════════════════════════════════════════════════════════════


class TestNarrowedProjectionDTO(unittest.TestCase):
    """EffectivePiExtensionEntry carries a canonical mounted-artifact
    identifier (artifact_id) alongside the SRI integrity string instead
    of a downloadable URL.

    These tests assert the DESIRED contract and FAIL until
    NpmArtifact is replaced with artifact_id + integrity."""

    _INTEGRITY = (
        "sha512-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
    )
    # Derived canonical artifact_id for _INTEGRITY.
    # algo=sha512, safe digest replaces +→- and /→_.
    _ARTIFACT_ID = (
        "sha512/"
        + _INTEGRITY.split("-", 1)[1].replace("+", "-").replace("/", "_")
        + ".tgz"
    )

    @staticmethod
    def _artifact_id_from(integrity: str) -> str:
        """Derive the canonical relative path from an SRI integrity.

        The artifact_id is ``<algorithm>/<digest>.tgz`` where *digest*
        is the URL-safe base64 encoding (``+`` → ``-``, ``/`` → ``_``).
        It is the deterministic suffix that, joined with the fixed
        container root ``/run/pi-cli/runtime-artifacts/``, forms the
        full container-side mount target.
        """
        algo, raw = integrity.split("-", 1)
        safe = raw.replace("+", "-").replace("/", "_")
        return f"{algo}/{safe}.tgz"

    # ── positive construction: artifact_id + integrity ────────────

    def test_artifact_id_and_integrity_both_accepted(self) -> None:
        """RED — the narrowed entry requires both a canonical
        artifact_id and the SRI integrity string, replacing
        NpmArtifact(url=..., integrity=...)."""
        expected_id = self._ARTIFACT_ID
        entry = EffectivePiExtensionEntry(
            package="@scope/pkg",
            version="2.3.4",
            artifact_id=expected_id,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertEqual(entry.package, "@scope/pkg")
        self.assertEqual(entry.version, "2.3.4")
        self.assertEqual(entry.artifact_id, expected_id)
        self.assertEqual(entry.integrity, self._INTEGRITY)
        self.assertEqual(entry.metadata_file, "package.json")

    def test_artifact_id_is_canonical_for_its_integrity(self) -> None:
        """RED — artifact_id is deterministically derived from
        integrity: ``<algorithm>/<safe_base64>.tgz``."""
        expected_id = self._ARTIFACT_ID
        self.assertTrue(expected_id.startswith("sha512/"))
        self.assertTrue(expected_id.endswith(".tgz"))
        # Prove the derivation is deterministic.
        derived = self._artifact_id_from(self._INTEGRITY)
        self.assertEqual(derived, expected_id)
        entry = EffectivePiExtensionEntry(
            package="p",
            version="1.0.0",
            artifact_id=expected_id,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertEqual(entry.artifact_id, expected_id)
        self.assertEqual(entry.integrity, self._INTEGRITY)

    # ── identity agreement: artifact_id must match integrity ─────

    def test_rejects_artifact_id_with_wrong_algorithm(self) -> None:
        """RED — an artifact_id whose algorithm prefix does not
        match the SRI algorithm is rejected."""
        wrong_id = "sha256/" + self._ARTIFACT_ID.split("/", 1)[1]
        with self.assertRaises(ValueError):
            EffectivePiExtensionEntry(
                package="p",
                version="1.0.0",
                artifact_id=wrong_id,
                integrity=self._INTEGRITY,  # sha512
                metadata_file="package.json",
            )

    def test_rejects_artifact_id_with_wrong_digest(self) -> None:
        """RED — an artifact_id whose digest bytes do not match
        integrity is rejected even when the algorithm agrees."""
        # Same algorithm, different digest.
        other_integrity = (
            "sha512-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
            "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=="
        )
        wrong_id = self._artifact_id_from(other_integrity)
        with self.assertRaises(ValueError):
            EffectivePiExtensionEntry(
                package="p",
                version="1.0.0",
                artifact_id=wrong_id,
                integrity=self._INTEGRITY,
                metadata_file="package.json",
            )

    # ── old artifact=NpmArtifact(...) rejected ───────────────────

    def test_artifact_field_rejected(self) -> None:
        """RED — the old artifact=NpmArtifact(...) keyword is no
        longer accepted on the narrowed entry."""
        valid_url = (
            "https://registry.npmjs.org/@scope/pkg/-/pkg-1.0.0.tgz"
        )
        with self.assertRaises(TypeError):
            EffectivePiExtensionEntry(
                package="@scope/pkg",
                version="1.0.0",
                artifact=NpmArtifact(
                    url=valid_url,
                    integrity=self._INTEGRITY,
                ),
                metadata_file="package.json",
            )

    def test_url_field_not_present_on_entry(self) -> None:
        """RED — the entry exposes no downloadable URL."""
        entry = EffectivePiExtensionEntry(
            package="p",
            version="1.0.0",
            artifact_id=self._ARTIFACT_ID,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertFalse(hasattr(entry, "url"))
        self.assertFalse(hasattr(entry, "artifact"))

    # ── each field is independently preserved ───────────────────

    def test_package_preserved(self) -> None:
        """RED — package identity survives the transition."""
        entry = EffectivePiExtensionEntry(
            package="@scope/pkg",
            version="1.0.0",
            artifact_id=self._ARTIFACT_ID,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertEqual(entry.package, "@scope/pkg")

    def test_version_preserved(self) -> None:
        """RED — exact version survives the transition."""
        entry = EffectivePiExtensionEntry(
            package="p",
            version="4.5.6",
            artifact_id=self._ARTIFACT_ID,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertEqual(entry.version, "4.5.6")

    def test_integrity_preserved_independently(self) -> None:
        """RED — the SRI integrity string is preserved as its own
        field, independent of artifact_id."""
        entry = EffectivePiExtensionEntry(
            package="p",
            version="1.0.0",
            artifact_id=self._ARTIFACT_ID,
            integrity=self._INTEGRITY,
            metadata_file="package.json",
        )
        self.assertEqual(entry.integrity, self._INTEGRITY)
        self.assertTrue(
            entry.integrity.startswith("sha512-"),
            "integrity must be a valid SRI string",
        )

    def test_metadata_file_preserved(self) -> None:
        """RED — safe metadata validation survives the transition."""
        entry = EffectivePiExtensionEntry(
            package="p",
            version="1.0.0",
            artifact_id=self._ARTIFACT_ID,
            integrity=self._INTEGRITY,
            metadata_file="nested/meta.json",
        )
        self.assertEqual(entry.metadata_file, "nested/meta.json")

    # ── integrity validation at construction ─────────────────────

    def test_rejects_malformed_integrity(self) -> None:
        """RED — the entry rejects an obviously invalid integrity
        string at construction time."""
        with self.assertRaises(ValueError):
            EffectivePiExtensionEntry(
                package="p",
                version="1.0.0",
                artifact_id=self._ARTIFACT_ID,
                integrity="not-an-sri-string",
                metadata_file="package.json",
            )


if __name__ == "__main__":
    unittest.main()
