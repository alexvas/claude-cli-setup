"""Presentation-neutral host materialization events."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Callable


class HostPhase(StrEnum):
    RELEASE_ACQUISITION = "release_acquisition"
    LOCKED_ASSEMBLY = "locked_assembly"
    DERIVED_VALIDATION = "derived_validation"
    DOCKER_TRANSITION = "docker_transition"


class HostPhaseState(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HostDiagnosticStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True)
class HostPhaseEvent:
    phase: HostPhase
    state: HostPhaseState

    def __post_init__(self) -> None:
        if not isinstance(self.phase, HostPhase) or not isinstance(self.state, HostPhaseState):
            raise TypeError("host phase events require fixed phase and state members")


@dataclass(frozen=True)
class HostDiagnosticEvent:
    phase: HostPhase
    stream: HostDiagnosticStream
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.phase, HostPhase) or not isinstance(self.stream, HostDiagnosticStream):
            raise TypeError("host diagnostic events require fixed phase and stream members")
        if not isinstance(self.text, str):
            raise TypeError("host diagnostic text must be a string")


HostBuildEvent = HostPhaseEvent | HostDiagnosticEvent
HostEventSink = Callable[[HostBuildEvent], None]


class GuardedHostEventSink:
    """Serialize presentation and permanently disable it after its first error."""

    def __init__(self, sink: HostEventSink) -> None:
        self._sink = sink
        self._lock = Lock()
        self._enabled = True

    def __call__(self, event: HostBuildEvent) -> None:
        with self._lock:
            if not self._enabled:
                return
            try:
                self._sink(event)
            except Exception:
                self._enabled = False


def guard_sink(sink: HostEventSink | None) -> HostEventSink | None:
    if sink is None or isinstance(sink, GuardedHostEventSink):
        return sink
    return GuardedHostEventSink(sink)


def emit(sink: HostEventSink | None, event: HostBuildEvent) -> None:
    """Present an event; guarded facade/orchestration sinks cannot affect work."""
    if sink is not None:
        try:
            sink(event)
        except Exception:
            # Direct SDK callers remain insulated; orchestration uses the
            # stateful guard above so one failure also disables later calls.
            pass
