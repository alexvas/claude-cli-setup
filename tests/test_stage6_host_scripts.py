"""Offline smoke tests for independently runnable Stage 6 host scripts."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from docker.verify_stage_6 import task_6_2 as verify_stage_6_2
from docker.verify_stage_6 import task_6_3 as verify_stage_6_3
from docker.verify_stage_6 import task_6_4 as verify_stage_6_4
from docker.verify_stage_6 import task_6_5 as verify_stage_6_5
from docker.verify_stage_6 import task_6_6 as verify_stage_6_6
from docker.verify_stage_6.evidence import compose_command


class TestStage6HostScripts(unittest.TestCase):
    def _evidence(self, directory: Path) -> dict:
        return json.loads((directory / "evidence.json").read_text(encoding="utf-8"))

    def test_compose_command_keeps_resolver_boundary(self):
        cmd = compose_command("build", "pi", override="x=y")
        self.assertEqual(cmd[:3], ["python3", "docker/versions.py", "compose"])
        self.assertIn("--", cmd)
        self.assertEqual(cmd[-2:], ["build", "pi"])

    def test_compose_progress_is_global(self):
        cmd = compose_command("--progress", "plain", "build", "pi")
        separator = cmd.index("--")
        self.assertEqual(cmd[separator + 1:], ["--progress", "plain", "build", "pi"])

    def test_task_6_2_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.assertEqual(verify_stage_6_2.main(["--dry-run", "--output-dir", str(out)]), 0)
            data = self._evidence(out)
            self.assertEqual(data["stage_task"], "6.2")
            self.assertTrue(data["dry_run"])

    def test_task_6_3_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            rc = verify_stage_6_3.main(["--dry-run", "--python-version", "3.14.7",
                                        "--inventory", "/tmp/experimental.toml",
                                        "--output-dir", str(out)])
            self.assertEqual(rc, 0)
            commands = self._evidence(out)["commands"]
            self.assertTrue(any("stages.toolchain.python.version=3.14.7" in c["argv"] for c in commands))
            self.assertTrue(any("/tmp/experimental.toml" in c["argv"] for c in commands))

    def test_task_6_4_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            pi_home = out / "pi-home"
            self.assertEqual(verify_stage_6_4.main([
                "--dry-run", "--output-dir", str(out),
            ]), 0)
            data = self._evidence(out)
            self.assertEqual(data["stage_task"], "6.4")
            self.assertTrue(any(
                any("install-pi-extensions.sh" in item for item in c["argv"])
                for c in data["commands"]
            ))
            self.assertTrue(any(
                any(str(pi_home) in item for item in c["argv"])
                for c in data["commands"]
            ))

    def test_task_6_5_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            rc = verify_stage_6_5.main(["--dry-run", "--case", "rtk=/tmp/rtk.toml",
                                        "--output-dir", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(self._evidence(out)["stage_task"], "6.5")

    def test_task_6_6_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            rc = verify_stage_6_6.main([
                "--dry-run", "--bad-checksum-inventory", "/tmp/bad-sha.toml",
                "--bad-base-digest-inventory", "/tmp/bad-base.toml",
                "--output-dir", str(out),
            ])
            self.assertEqual(rc, 0)
            data = self._evidence(out)
            self.assertEqual(data["stage_task"], "6.6")
            self.assertTrue(any(c["skipped"] for c in data["commands"]))


if __name__ == "__main__":
    unittest.main()
