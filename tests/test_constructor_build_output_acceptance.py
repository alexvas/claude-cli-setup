"""End-to-end Docker build-output acceptance tests using a fake docker binary."""
from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_FAKE_DOCKER = """#!{python}
import os
import sys
import time
scenario = os.environ['FAKE_DOCKER_SCENARIO']
if scenario == 'stream-success':
    print('first', flush=True)
    release_file = os.environ['FAKE_DOCKER_RELEASE_FILE']
    while not os.path.exists(release_file):
        time.sleep(.01)
    print('second', flush=True)
elif scenario == 'stream-failure':
    print('UNIQUE-DOCKER-FAILURE', file=sys.stderr, flush=True)
    sys.exit(23)
elif scenario == 'json-success':
    print('docker-stdout', flush=True)
    print('docker-stderr', file=sys.stderr, flush=True)
elif scenario == 'json-failure':
    print('docker-failure-stdout', flush=True)
    print('docker-failure-stderr', file=sys.stderr, flush=True)
    sys.exit(29)
else:
    raise AssertionError(scenario)
"""


class TestBuildOutputEndToEnd(unittest.TestCase):
    """Exercise CLI → orchestration → subprocess executor → renderer."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "repo"
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source, cls.root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".docker-generated", ".docker-local",
        ))
        fake_dir = cls.root / "fake-bin"
        fake_dir.mkdir()
        fake = fake_dir / "docker"
        fake.write_text(_FAKE_DOCKER.format(python=sys.executable), encoding="utf-8")
        fake.chmod(0o755)
        cls.fake_dir = fake_dir
        cls.release_dir = cls.root / "release-signals"
        cls.release_dir.mkdir()
        cls._release_number = 0

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _env(self, scenario: str) -> tuple[dict[str, str], Path]:
        type(self)._release_number += 1
        release_file = self.release_dir / f"release-{type(self)._release_number}"
        env = os.environ.copy()
        env.update({
            "PATH": f"{self.fake_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_SCENARIO": scenario,
            "FAKE_DOCKER_RELEASE_FILE": str(release_file),
        })
        return env, release_file

    def _command(self, *args: str) -> list[str]:
        return [sys.executable, str(self.root / "docker/docker-constructor.py"), *args]

    def test_text_progress_is_visible_before_cli_exits(self):
        env, release_file = self._env("stream-success")
        proc = subprocess.Popen(
            self._command("build", "-y"), cwd=self.root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            assert proc.stdout is not None
            ready, _, _ = select.select([proc.stdout], [], [], 5)
            self.assertTrue(ready, "first Docker progress line was buffered until CLI exit")
            self.assertEqual("first\n", proc.stdout.readline())
            self.assertIsNone(proc.poll(), "CLI exited before first progress became observable")
            release_file.touch()
            stdout_tail, stderr = proc.communicate(timeout=5)
            self.assertEqual(0, proc.returncode, stderr)
            self.assertIn("second", stdout_tail)
        finally:
            release_file.touch(exist_ok=True)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()

    def test_streamed_failure_is_not_replayed_and_maps_operational_exit(self):
        env, _ = self._env("stream-failure")
        completed = subprocess.run(
            self._command("build", "-y"), cwd=self.root, env=env,
            capture_output=True, text=True, timeout=3,
        )
        self.assertEqual(4, completed.returncode)
        self.assertEqual(1, completed.stderr.count("UNIQUE-DOCKER-FAILURE"))
        self.assertIn("23", completed.stderr)

    def test_json_success_is_one_isolated_document(self):
        env, _ = self._env("json-success")
        completed = subprocess.run(
            self._command("--output", "json", "build", "-y"), cwd=self.root,
            env=env, capture_output=True, text=True, timeout=3,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.stdout.strip(), json.dumps(payload, indent=2, sort_keys=True))
        self.assertEqual("success", payload["status"])
        self.assertEqual("docker-stdout\n", payload["data"]["stdout"])
        self.assertEqual("docker-stderr\n", payload["data"]["stderr"]) 
        self.assertEqual("", completed.stderr)

    def test_json_failure_contains_captured_diagnostics_and_operational_exit(self):
        env, _ = self._env("json-failure")
        completed = subprocess.run(
            self._command("--output", "json", "build", "-y"), cwd=self.root,
            env=env, capture_output=True, text=True, timeout=3,
        )
        self.assertEqual(4, completed.returncode)
        self.assertEqual("", completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("operational", payload["status"])
        self.assertEqual({
            "return_code": 29,
            "stdout": "docker-failure-stdout\n",
            "stderr": "docker-failure-stderr\n",
            "output_policy": "captured",
        }, {key: payload["data"][key] for key in
            ("return_code", "stdout", "stderr", "output_policy")})
