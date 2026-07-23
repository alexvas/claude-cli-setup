"""Thin wrapper that re-exports the docker.versioning package.

This module exists for backward compatibility so existing imports like
``from docker.versions import load_inventory`` continue to work.
The real implementation lives in docker/versioning/.
"""
from __future__ import annotations

if __package__:
    from .versioning.inventory import load_inventory, validate_inventory
    from .versioning.errors import (
        VersionConfigError,
        InventoryError,
        VersionSyntaxError,
        ConstraintSyntaxError,
    )
    from .versioning.constraints import (
        NumericVersion,
        ConstraintClause,
        Constraint,
        parse_numeric_version,
        parse_constraint,
        validate_constraint_consistency,
    )
    from .versioning.model import (
        ArtifactEntry,
        BaseStage,
        DockerRegistrySource,
        DockerRegistryUpdate,
        FdPrebuiltStage,
        GitHubReleaseSource,
        GitHubReleaseUpdate,
        GitRefUpdate,
        GitSource,
        Inventory,
        NodeEntry,
        NpmSource,
        NpmToolEntry,
        NpmUpdate,
        OhMyZshEntry,
        OpenSpecToolsStage,
        OverridePolicy,
        PiExtensionEntry,
        PiToolsStage,
        PrebuiltToolEntry,
        PyPiSource,
        PyPiUpdate,
        PythonEntry,
        RtkPrebuiltStage,
        RuntimeStage,
        RustChannelSource,
        RustChannelUpdate,
        RustEntry,
        Stages,
        ToolchainStage,
        TyEntry,
        UvEntry,
        UvPythonSource,
        UvPythonUpdate,
    )
else:
    from versioning.inventory import load_inventory, validate_inventory  # type: ignore[import-not-found]
    from versioning.errors import (  # type: ignore[import-not-found]
        VersionConfigError,
        InventoryError,
        VersionSyntaxError,
        ConstraintSyntaxError,
    )
    from versioning.constraints import (  # type: ignore[import-not-found]
        NumericVersion,
        ConstraintClause,
        Constraint,
        parse_numeric_version,
        parse_constraint,
        validate_constraint_consistency,
    )
    from versioning.model import (  # type: ignore[import-not-found]
        ArtifactEntry,
        BaseStage,
        DockerRegistrySource,
        DockerRegistryUpdate,
        FdPrebuiltStage,
        GitHubReleaseSource,
        GitHubReleaseUpdate,
        GitRefUpdate,
        GitSource,
        Inventory,
        NodeEntry,
        NpmSource,
        NpmToolEntry,
        NpmUpdate,
        OhMyZshEntry,
        OpenSpecToolsStage,
        OverridePolicy,
        PiExtensionEntry,
        PiToolsStage,
        PrebuiltToolEntry,
        PyPiSource,
        PyPiUpdate,
        PythonEntry,
        RtkPrebuiltStage,
        RuntimeStage,
        RustChannelSource,
        RustChannelUpdate,
        RustEntry,
        Stages,
        ToolchainStage,
        TyEntry,
        UvEntry,
        UvPythonSource,
        UvPythonUpdate,
    )

if __package__:
    from .versioning.cli import main
else:
    from versioning.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
