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


# ── Stub ──────────────────────────────────────────────────────────────


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
    raise NotImplementedError("collect_evidence — 12.3 RED")
