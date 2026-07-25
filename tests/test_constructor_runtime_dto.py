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


if __name__ == "__main__":
    unittest.main()
