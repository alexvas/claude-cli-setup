"""Shared standard-library helpers for Stage 6 host verification scripts."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandEvidence:
    argv: tuple[str, ...]
    cwd: str
    returncode: int | None
    duration_seconds: float
    stdout_file: str | None
    stderr_file: str | None
    skipped: bool = False


class EvidenceRunError(RuntimeError):
    """A verification command failed."""


class EvidenceCollector:
    def __init__(self, output_dir: Path, *, dry_run: bool = False) -> None:
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run
        self.commands: list[CommandEvidence] = []
        self.notes: dict[str, object] = {}

    def run(
        self,
        name: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        check: bool = True,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = tuple(str(v) for v in argv)
        stdout_path = self.output_dir / f"{name}.stdout.log"
        stderr_path = self.output_dir / f"{name}.stderr.log"
        print("+", shlex.join(command))
        if self.dry_run:
            self.commands.append(CommandEvidence(
                argv=command, cwd=str(cwd.resolve()), returncode=None,
                duration_seconds=0.0, stdout_file=None, stderr_file=None,
                skipped=True,
            ))
            return subprocess.CompletedProcess(command, 0, "", "")

        started = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=cwd,
                env=dict(env) if env is not None else None,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            stdout_path.write_text(exc.stdout or "", encoding="utf-8")
            stderr_path.write_text(exc.stderr or "", encoding="utf-8")
            self.commands.append(CommandEvidence(
                argv=command, cwd=str(cwd.resolve()), returncode=124,
                duration_seconds=duration, stdout_file=str(stdout_path),
                stderr_file=str(stderr_path),
            ))
            raise EvidenceRunError(f"{name}: timed out after {timeout}s") from exc
        except OSError as exc:
            duration = time.monotonic() - started
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            self.commands.append(CommandEvidence(
                argv=command, cwd=str(cwd.resolve()), returncode=126,
                duration_seconds=duration, stdout_file=str(stdout_path),
                stderr_file=str(stderr_path),
            ))
            raise EvidenceRunError(f"{name}: cannot execute command; see {stderr_path}") from exc

        duration = time.monotonic() - started
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        self.commands.append(CommandEvidence(
            argv=command, cwd=str(cwd.resolve()), returncode=proc.returncode,
            duration_seconds=duration, stdout_file=str(stdout_path),
            stderr_file=str(stderr_path),
        ))
        if check and proc.returncode != 0:
            raise EvidenceRunError(
                f"{name}: command exited {proc.returncode}; see {stderr_path}"
            )
        return proc

    def expect_failure(self, name: str, argv: Sequence[str], *, cwd: Path,
                       env: Mapping[str, str] | None = None,
                       timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        proc = self.run(name, argv, cwd=cwd, env=env, check=False, timeout=timeout)
        if not self.dry_run and proc.returncode == 0:
            raise EvidenceRunError(f"{name}: command unexpectedly succeeded")
        return proc

    def add_file(self, name: str, path: Path) -> None:
        if not path.is_file():
            self.notes[name] = {"path": str(path), "missing": True}
            return
        try:
            data = path.read_bytes()
        except OSError as exc:
            self.notes[name] = {
                "path": str(path.resolve()),
                "unreadable": True,
                "error": str(exc),
            }
            if not self.dry_run:
                raise EvidenceRunError(f"cannot read evidence file {path}: {exc}") from exc
            return
        self.notes[name] = {
            "path": str(path.resolve()),
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def finish(self, *, stage_task: str, success: bool) -> Path:
        result = {
            "stage_task": stage_task,
            "success": success,
            "dry_run": self.dry_run,
            "generated_at_epoch": int(time.time()),
            "commands": [asdict(c) for c in self.commands],
            "notes": self.notes,
        }
        path = self.output_dir / "evidence.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def repo_root(script_file: str) -> Path:
    """Find the repository root from a script nested under docker/."""
    current = Path(script_file).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "docker-constructor.toml").is_file() and (candidate / "docker").is_dir():
            return candidate
    raise EvidenceRunError(f"cannot locate repository root from {script_file}")


def resolved_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if extra:
        env.update({str(k): str(v) for k, v in extra.items()})
    return env


def prepare_pi_home(
    collector: EvidenceCollector,
    *,
    root: Path,
    image: str,
    path: Path,
    reset: bool,
) -> Path:
    """Create a Pi home and install the extensions configured in the image."""
    pi_home = path.resolve()
    if not collector.dry_run:
        if reset and pi_home.exists():
            shutil.rmtree(pi_home)
        pi_home.mkdir(parents=True, exist_ok=True)
    collector.run(
        "install-extensions",
        ["docker", "run", "--rm", "-v", f"{pi_home}:/home/dev/.pi",
         image, "/home/dev/install-pi-extensions.sh"],
        cwd=root,
        timeout=1800,
    )
    return pi_home


def compose_command(*args: str, inventory: Path | None = None,
                    override: str | None = None,
                    effective_output: Path | None = None) -> list[str]:
    command = ["python3", "docker/versions.py", "compose"]
    if inventory is not None:
        command += ["--inventory", str(inventory)]
    if override is not None:
        command += ["--override", override]
    if effective_output is not None:
        command += ["--effective-inventory-output", str(effective_output)]
    command += ["--", *args]
    return command
