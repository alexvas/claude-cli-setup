"""Regression tests for maintenance-script cache-root preparation."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


_ROOT = Path(__file__).parents[1]


def _write_probe(directory: Path, name: str, marker: Path) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' {name} >> {marker}\nexit 97\n")
    path.chmod(0o755)


class TestMaintenanceCachePreparation(unittest.TestCase):
    def _environment(self, base: Path, marker: Path) -> dict[str, str]:
        probes = base / "probes"
        probes.mkdir()
        for name in ("find", "rm"):
            _write_probe(probes, name, marker)
        env = os.environ.copy()
        env.update({
            "HOME": str(base / "home"),
            "XDG_CACHE_HOME": str(base / "xdg"),
            "PATH": str(probes) + os.pathsep + env["PATH"],
            "PYTHONPATH": str(_ROOT),
        })
        (base / "home").mkdir()
        (base / "xdg").mkdir()
        return env

    def _inventory(self, base: Path, cache_dir: Path) -> Path:
        inventory = base / "fixture.toml"
        inventory.write_text("schema = 1\n")
        inventory.with_name("docker-constructor.local.toml").write_text(
            f"[cache]\ndir = {str(cache_dir)!r}\n"
        )
        return inventory

    def test_evidence_rejects_symlinked_local_root_before_find(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            marker = base / "operations"
            outside = base / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_bytes(b"unchanged")
            selected = base / "selected-cache"
            selected.symlink_to(outside, target_is_directory=True)
            inventory = self._inventory(base, selected)
            result = subprocess.run(
                [str(_ROOT / "docker/collect-runtime-artifact-evidence.sh"),
                 "--inventory", str(inventory), "--output-dir", str(base / "evidence")],
                env=self._environment(base, marker), capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink", result.stderr.lower())
            self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else "")
            self.assertEqual(sentinel.read_bytes(), b"unchanged")

    def test_acceptance_rejects_unsafe_local_root_before_rm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            marker = base / "operations"
            env = self._environment(base, marker)
            xdg = Path(env["XDG_CACHE_HOME"])
            sentinel = xdg / "sentinel"
            sentinel.write_bytes(b"unchanged")
            inventory = self._inventory(base, xdg)
            result = subprocess.run(
                [str(_ROOT / "docker/collect-runtime-artifact-acceptance.sh"),
                 "--inventory", str(inventory), "--output-dir", str(base / "evidence"),
                 "--fresh-cache"],
                env=env, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("dedicated", result.stderr.lower())
            self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else "")
            self.assertEqual(sentinel.read_bytes(), b"unchanged")


if __name__ == "__main__":
    unittest.main()
