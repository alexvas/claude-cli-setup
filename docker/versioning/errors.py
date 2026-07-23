"""Exception hierarchy for docker versioning.

All messages accept or construct dot-path identifiers so callers can
pinpoint the offending TOML key.
"""
from __future__ import annotations


class VersionConfigError(ValueError):
    """Base for all docker/versioning errors."""


class InventoryError(VersionConfigError):
    """Inventory structure or value is invalid."""


class VersionSyntaxError(VersionConfigError):
    """Version string cannot be parsed."""


class ConstraintSyntaxError(VersionConfigError):
    """Constraint string cannot be parsed or is contradictory."""
