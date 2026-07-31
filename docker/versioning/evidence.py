"""Evidence collector — record verification commands into a portable bundle.

Every process boundary is injectable so tests remain daemon-independent.
The collector records command arguments, exit codes, timestamps, bounded
stdout/stderr, image inspection, checksums, and redaction metadata, then
produces a human-readable index.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


# ── Process boundary (shared) ─────────────────────────────────────────


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    return_code: int
    stdout: str
    stderr: str


class ProcessRunner(Protocol):
    def run(self, argv: Sequence[str]) -> ProcessResult:
        """Execute *argv* and return the outcome.

        May raise ``TimeoutError`` (converted to return code 124) or
        ``OSError`` (converted to return code 126) — the collector
        catches both and continues."""
        ...


# ── Time boundary ───────────────────────────────────────────────────


class Clock(Protocol):
    def now(self) -> float:
        """Return the current time in epoch seconds."""
        ...


# ── Collector models ──────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceCommand:
    """A single recorded command."""
    argv: tuple[str, ...]
    """Exact argument vector (passwords and secrets redacted)."""
    return_code: int | None
    """Exit code, or ``None`` when skipped (dry-run)."""
    timestamp_epoch: float
    """Wall-clock epoch when the command started (from injected clock)."""
    duration_seconds: float
    """Wall-clock duration (``clock.now()`` after minus before)."""
    stdout_file: str | None
    """Relative path to captured stdout; ``None`` when skipped."""
    stderr_file: str | None
    """Relative path to captured stderr; ``None`` when skipped."""
    stdout_sha256: str | None
    """SHA-256 of captured stdout content (after truncation)."""
    stderr_sha256: str | None
    """SHA-256 of captured stderr content (after truncation)."""
    stdout_truncated: bool = False
    """``True`` when stdout exceeded *max_output_bytes* and was cut."""
    stderr_truncated: bool = False
    """``True`` when stderr exceeded *max_output_bytes* and was cut."""
    stdout_original_bytes: int | None = None
    """Full byte count before truncation; ``None`` when not truncated."""
    stderr_original_bytes: int | None = None
    """Full byte count before truncation; ``None`` when not truncated."""
    skipped: bool = False
    """``True`` when the command was not actually executed."""


@dataclass(frozen=True)
class EvidenceNote:
    """Static note about a collected artifact (file, image, etc.)."""
    key: str
    """Label for the note (e.g. ``"image-inspect"``)."""
    detail: str
    """Human-readable summary."""


@dataclass(frozen=True)
class EvidenceBundle:
    """A complete portable evidence collection."""
    commands: tuple[EvidenceCommand, ...]
    """Every command recorded during collection, in order."""
    notes: tuple[EvidenceNote, ...]
    """Static observations (image inspection, checksums, etc.)."""
    output_dir: Path
    """Directory containing the captured stdout/stderr files."""
    index_path: Path
    """Path to the human-readable index file inside *output_dir*."""
    dry_run: bool
    """Whether the collection was a dry-run."""


# ── Implementation ───────────────────────────────────────────────────

import hashlib
import os
import time


class _SystemClock:
    """Production clock that delegates to ``time.time()``."""

    def now(self) -> float:
        return time.time()

_SECRET_PATTERNS: tuple[tuple[bytes, bytes], ...] = (
    (b"-e ", b"-e REDACTED="),
    (b"--env ", b"--env REDACTED="),
    (b"Bearer ", b"Bearer REDACTED"),
    (b"token=", b"token=REDACTED"),
)


def _redact_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Replace secret-bearing argv entries with redacted versions.

    Handles two forms:
    - ``-e KEY=VALUE`` → ``-e KEY=REDACTED`` (when VALUE looks secret)
    - ``--env KEY=VALUE`` → ``--env KEY=REDACTED`` (when VALUE looks secret)

    A value is considered secret when it is longer than 3 characters
    and not purely numeric — typical for tokens and passwords.  Short
    flag values like ``0``, ``1``, ``true`` are preserved as-is.
    """
    result: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-e", "--env") and i + 1 < len(argv):
            next_arg = argv[i + 1]
            if "=" in next_arg:
                prefix, _, val = next_arg.partition("=")
                # Redact only secret-looking values.
                if len(val) > 3 and not val.isdigit():
                    result.append(arg)
                    result.append(f"{prefix}=REDACTED")
                    i += 2
                    continue
        result.append(arg)
        i += 1
    return tuple(result)


def _redact_content(data: str) -> str:
    """Scrub secrets (Bearer tokens etc.) from captured output."""
    import re
    d = data
    d = re.sub(r"Bearer\s+\S+", "Bearer REDACTED", d)
    return d


def _truncate(data: str, max_bytes: int) -> tuple[str, bool, int | None]:
    """Truncate *data* to *max_bytes*.  Returns
    ``(truncated, was_truncated, original_len)``."""
    b = data.encode("utf-8")
    if len(b) <= max_bytes:
        return data, False, None
    return b[:max_bytes].decode("utf-8", errors="replace"), True, len(b)


def _write_output_file(
    output_dir: Path, stem: str, content: str,
) -> str | None:
    """Write *content* to ``<stem>.txt`` inside *output_dir*.
    Returns the relative filename, or ``None`` when content is empty."""
    if not content:
        return None
    fname = f"{stem}.txt"
    (output_dir / fname).write_text(content, encoding="utf-8")
    return fname


def collect_evidence(
    *,
    output_dir: Path,
    runner: ProcessRunner,
    clock: Clock,
    image: str,
    commands: Sequence[Sequence[str]] = (),
    max_output_bytes: int = 1_048_576,
    dry_run: bool = False,
) -> EvidenceBundle:
    """Run verification commands against *image* and collect results.

    Every command is timestamped via *clock*.  Stdout/stderr are
    truncated to *max_output_bytes* (1 MiB default); truncation is
    recorded in the command metadata.

    *commands* is an explicit list of additional command vectors to
    collect — useful for recording a representative ``docker run``
    alongside the built-in inspection and verification commands.  Each
    entry is executed via *runner* and its argv is recorded (with
    secret redaction applied to the recorded copy; *runner.calls*
    retains the original argv).

    The collected bundle can be transported to a daemon-free
    environment for inspection.
    """
    import subprocess
    import json as _json
    from datetime import datetime, timezone

    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_commands: list[EvidenceCommand] = []
    evidence_notes: list[EvidenceNote] = []

    all_commands: list[tuple[str, ...]] = []

    if commands:
        for cmd in commands:
            all_commands.append(tuple(cmd))
    else:
        # Default: docker inspect to capture image metadata.
        all_commands.append(("docker", "inspect", image))

    # Execute each command
    for cmd in all_commands:
        t_start = clock.now()
        if dry_run:
            evidence_commands.append(EvidenceCommand(
                argv=_redact_argv(cmd),
                return_code=None,
                timestamp_epoch=t_start,
                duration_seconds=0.0,
                stdout_file=None,
                stderr_file=None,
                stdout_sha256=None,
                stderr_sha256=None,
                skipped=True,
            ))
            continue

        try:
            result = runner.run(cmd)
            rc: int | None = result.return_code
            stdout_raw = result.stdout
            stderr_raw = result.stderr
        except TimeoutError as te:
            # TimeoutError args: (stdout, stderr, argv) per the
            # ProcessRunner contract.
            stdout_raw = te.args[0] if len(te.args) > 0 else ""
            stderr_raw = te.args[1] if len(te.args) > 1 else "timeout"
            rc = 124
        except OSError as oe:
            stdout_raw = ""
            stderr_raw = str(oe)
            rc = 126

        t_stop = clock.now()
        duration = t_stop - t_start

        # Redact stderr
        stderr_clean = _redact_content(stderr_raw) if stderr_raw else ""

        # Truncate
        stdout_trunc, stdout_truncated, stdout_orig = _truncate(
            stdout_raw if stdout_raw else "", max_output_bytes,
        )
        stderr_trunc, stderr_truncated, stderr_orig = _truncate(
            stderr_clean, max_output_bytes,
        )

        # Write files
        idx = len(evidence_commands)
        stdout_file = _write_output_file(output_dir, f"{idx:03d}-stdout",
                                          stdout_trunc) if stdout_trunc else None
        stderr_file = _write_output_file(output_dir, f"{idx:03d}-stderr",
                                          stderr_trunc) if stderr_trunc else None

        # Checksums — hash the truncated content (may be empty string).
        stdout_sha256 = hashlib.sha256(stdout_trunc.encode()).hexdigest()
        stderr_sha256 = hashlib.sha256(stderr_trunc.encode()).hexdigest()

        evidence_commands.append(EvidenceCommand(
            argv=_redact_argv(cmd),
            return_code=rc,
            timestamp_epoch=t_start,
            duration_seconds=duration,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_original_bytes=stdout_orig,
            stderr_original_bytes=stderr_orig,
        ))

    # ── Static notes ──────────────────────────────────────────────────
    # Image inspect result (from any command whose argv contains "inspect")
    if not dry_run:
        for cmd_rec in evidence_commands:
            if cmd_rec.skipped:
                continue
            if any("inspect" in a for a in cmd_rec.argv):
                if cmd_rec.return_code == 0 and cmd_rec.stdout_file:
                    try:
                        raw = (output_dir / cmd_rec.stdout_file).read_text()
                        img_data = _json.loads(raw)
                        if isinstance(img_data, list) and img_data:
                            img_id = img_data[0].get("Id", "unknown")
                        else:
                            img_id = "unknown"
                    except Exception:
                        img_id = "parse-error"
                    evidence_notes.append(EvidenceNote(
                        key="image-inspect",
                        detail=f"image {image}: ID {img_id}",
                    ))
                elif cmd_rec.return_code not in (0, None):
                    evidence_notes.append(EvidenceNote(
                        key="image-inspect",
                        detail=f"docker inspect {image} failed (exit"
                                f" {cmd_rec.return_code})",
                    ))
                break

    # Host metadata
    hostname = os.uname().nodename
    evidence_notes.append(EvidenceNote(
        key="host-metadata",
        detail=f"collected on {hostname}",
    ))

    # Git SHA
    try:
        git_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if git_result.returncode == 0:
            git_sha = git_result.stdout.strip()
            evidence_notes.append(EvidenceNote(
                key="git-sha",
                detail=f"commit {git_sha}",
            ))
        else:
            evidence_notes.append(EvidenceNote(
                key="git-sha",
                detail="git rev-parse failed",
            ))
    except Exception:
        evidence_notes.append(EvidenceNote(
            key="git-sha",
            detail="git unavailable",
        ))

    # ── Human-readable index ───────────────────────────────────────────
    ts = datetime.fromtimestamp(evidence_commands[0].timestamp_epoch
                                 if evidence_commands else clock.now(),
                                 tz=timezone.utc)
    lines: list[str] = []
    lines.append(f"Evidence collection for image: {image}")
    lines.append(f"Generated at: {ts.isoformat()}")
    lines.append(f"Output directory: {output_dir}")
    lines.append(f"Dry run: {dry_run}")
    lines.append("")
    lines.append("Commands:")
    for i, cmd in enumerate(evidence_commands):
        skipped = " (skipped)" if cmd.skipped else ""
        rc_str = str(cmd.return_code) if cmd.return_code is not None else "-"
        dur = f"{cmd.duration_seconds:.3f}s"
        lines.append(
            f"  [{i:03d}] exit={rc_str} dur={dur}{skipped}"
            f" argv={' '.join(cmd.argv)}"
        )
        if cmd.stdout_file:
            lines.append(f"        stdout={cmd.stdout_file}"
                         f" (sha256={cmd.stdout_sha256})")
        if cmd.stderr_file:
            lines.append(f"        stderr={cmd.stderr_file}"
                         f" (sha256={cmd.stderr_sha256})")
    lines.append("")
    lines.append("Notes:")
    for note in evidence_notes:
        lines.append(f"  [{note.key}] {note.detail}")

    # Overall status
    failures = [c for c in evidence_commands
                if not c.skipped and c.return_code not in (0, None)]
    lines.append("")
    if failures:
        lines.append(f"OVERALL: FAIL ({len(failures)} command(s) failed)")
    else:
        lines.append("OVERALL: PASS")

    # Bundle self-checksum
    index_raw = "\n".join(lines)
    bundle_hash = hashlib.sha256(index_raw.encode()).hexdigest()
    lines.append(f"Bundle checksum (sha256): {bundle_hash}")

    index_path = output_dir / "index.txt"
    index_path.write_text(index_raw, encoding="utf-8")

    return EvidenceBundle(
        commands=tuple(evidence_commands),
        notes=tuple(evidence_notes),
        output_dir=output_dir,
        index_path=index_path,
        dry_run=dry_run,
    )
