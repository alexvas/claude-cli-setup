"""Consistency checks for the maintained version-management documentation."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READMES = ("README.md", "README.en.md", "README.zh.md")


class TestVersionDocumentation(unittest.TestCase):
    def _documents(self):
        for name in READMES:
            yield name, (ROOT / name).read_text(encoding="utf-8")

    def test_all_readmes_document_canonical_inventory_workflow(self):
        # Direct invocation is the canonical documented form.
        required = (
            "versions.toml",
            "./docker/versions.py validate",
            "./docker/versions.py env",
            "./docker/versions.py compose",
            "--override stages.toolchain.python.version=X.Y.Z",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)

    def test_all_readmes_allow_interpreter_compatibility_reference(self):
        """READMEs may reference the interpreter-prefixed form for
        compatibility, but the canonical direct form must be present."""
        direct_forms = (
            "./docker/versions.py validate",
            "./docker/versions.py env",
            "./docker/versions.py compose",
            "./docker/versions.py check-updates",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in direct_forms:
                    self.assertIn(
                        token, text,
                        f"{name} must contain direct canonical form: {token}",
                    )

    def test_all_readmes_document_restricted_override_grammar(self):
        for name, text in self._documents():
            with self.subTest(readme=name):
                self.assertIn("==, >, >=, <, <=", text)
                self.assertIn("X.Y.Z", text)
                self.assertIn("prerelease", text.lower())

    def test_all_readmes_document_explicit_update_modes(self):
        required = (
            "./docker/versions.py check-updates",
            "--only stages.toolchain.python",
            "--suggest",
            "--strict",
            "--fail-on-outdated",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)
                self.assertRegex(text, re.compile(r"non-mutating", re.IGNORECASE))

    def test_all_readmes_document_reproducibility_and_ownership(self):
        required = (
            "Debian",
            "OCI",
            "split-rtk-fd-prebuilt",
            "pin-pi-read-npm",
        )
        for name, text in self._documents():
            with self.subTest(readme=name):
                for token in required:
                    self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
