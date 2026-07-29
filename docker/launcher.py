"""Project launcher — project selection, pi-N allocation, and
run-vector assembly for ``docker-constructor.py run``.

This module owns:
  - :class:`ProjectSelection` — resolved project paths ready for rendering
  - :func:`resolve_project_selection` — CLI-flag → selection with precedence
  - :func:`allocate_pi_name` — lowest-free pi-N from container inspection
  - :func:`build_run_inputs` — selection → :class:`RunRenderInputs`

All Docker interaction happens through injected boundaries
(:class:`ContainerNameInspector`).  No module here invokes Docker,
reads the filesystem, or prompts the user directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


# ═══════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════


class NoMainProjectError(Exception):
    """Raised when no main project can be determined."""


class ContainerInspectError(Exception):
    """Raised when Docker container inspection fails."""


# ═══════════════════════════════════════════════════════════════════
# Value objects
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProjectSelection:
    """Resolved project selection ready for launch-vector assembly.

    *main_project* is always a non-empty absolute path.
    *optional_projects* preserves insertion order with no duplicates.
    """

    main_project: str
    optional_projects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.main_project or not os.path.isabs(self.main_project):
            raise ValueError(
                f"main_project must be a non-empty absolute path, "
                f"got {self.main_project!r}"
            )
        for i, p in enumerate(self.optional_projects):
            if not p or not os.path.isabs(p):
                raise ValueError(
                    f"optional_projects[{i}] must be a non-empty "
                    f"absolute path, got {p!r}"
                )


# ═══════════════════════════════════════════════════════════════════
# Injected boundaries
# ═══════════════════════════════════════════════════════════════════


class ContainerNameInspector(Protocol):
    """Injected Docker container-name inspection boundary.

    Returns an unordered set of existing container names visible
    to ``docker ps -a``.  Raises :class:`ContainerInspectError` when
    Docker is unavailable or output cannot be parsed.
    """

    def list_names(self) -> set[str]:
        ...


class ProjectSelector(Protocol):
    """Injected interactive project-selection boundary (TUI).

    Returns a resolved :class:`ProjectSelection` or ``None`` when
    the user cancels.  The caller owns validation and error mapping.
    """

    def select(self) -> ProjectSelection | None:
        ...


# ═══════════════════════════════════════════════════════════════════
# Public API (stubs — to be implemented in 11.4)
# ═══════════════════════════════════════════════════════════════════


def resolve_project_selection(
    *,
    main_project: str | None = None,
    projects: tuple[str, ...] = (),
    tui: bool = False,
    base_project_dir: str | None = None,
    selector: ProjectSelector | None = None,
) -> ProjectSelection:
    """Resolve main and optional projects from CLI flags.

    Precedence:
    1. Explicit *main_project*
    2. TUI selection via *selector* (when *tui* is ``True``)
    3. Documented automatic selection (if retained)
    4. Raise :class:`NoMainProjectError`
    """
    raise NotImplementedError("resolve_project_selection")


def allocate_pi_name(inspector: ContainerNameInspector) -> str:
    """Return the lowest free ``pi-N`` container name.

    Inspects existing containers via *inspector* and returns the
    smallest N ≥ 1 such that ``pi-N`` is not in use.  Allocation is
    best-effort — another process may claim the name before
    ``docker run`` executes.
    """
    raise NotImplementedError("allocate_pi_name")


def build_run_inputs(
    *,
    selection: ProjectSelection,
    image: str,
    container_name: str,
    pi_home_host: str,
    projection_host_path: str,
    projection_container_path: str,
    gateway: str = "host-gateway",
    tty: bool = True,
    stdin_open: bool = True,
    chown_on_start: str | None = None,
):
    """Build :class:`~docker.versioning.rendering.RunRenderInputs`
    from a resolved :class:`ProjectSelection` and runtime parameters.
    """
    raise NotImplementedError("build_run_inputs")
