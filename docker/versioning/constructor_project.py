"""Constructor-project path selection and fixed project-owned paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConstructorProject:
    """One normalized physical constructor-project directory."""

    root: Path

    @property
    def inventory(self) -> Path:
        return self.root / "docker-constructor.toml"

    @property
    def local_config(self) -> Path:
        return self.root / "docker-constructor.local.toml"

    @property
    def dockerfile(self) -> Path:
        return self.root / "Dockerfile"

    @property
    def dotenv(self) -> Path:
        return self.root / ".env"

    @property
    def local_inputs(self) -> Path:
        return self.root / ".docker-local"


def resolve_constructor_project(
    selected: str | Path | None,
    *,
    cwd: Path | None = None,
) -> ConstructorProject:
    """Resolve *selected*, or CWD when omitted, to an existing directory."""

    process_cwd = Path.cwd() if cwd is None else Path(cwd)
    candidate = process_cwd if selected is None else Path(selected)
    if not candidate.is_absolute():
        candidate = process_cwd / candidate
    root = candidate.resolve()
    if not root.exists():
        raise ValueError(f"constructor project directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"constructor project path is not a directory: {root}")
    return ConstructorProject(root=root)
