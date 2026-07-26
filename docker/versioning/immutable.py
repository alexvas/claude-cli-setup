"""Immutable value helpers — internal utility with no domain dependencies.

The ``deep_freeze`` function is the single canonical implementation
used by the facade (``CommandRequest``), transports
(``TransportConfig``), and any future dataclass that must guarantee
recursive immutability.
"""

from __future__ import annotations

from types import MappingProxyType


def deep_freeze(value: object) -> object:
    """Recursively freeze mutable containers to immutable equivalents.

    * ``list`` → ``tuple``
    * ``dict`` / ``Mapping`` (including ``MappingProxyType``) →
      ``MappingProxyType`` with recursively frozen children
    * ``set`` → ``frozenset``
    * Values inside containers are frozen recursively.
    * Scalars (str, int, float, bool, None, …) are returned as-is.
    """
    if isinstance(value, (frozenset, str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(v) for v in value)
    if isinstance(value, (dict, MappingProxyType)) or hasattr(value, "items"):
        # Always rebuild — proxies may contain mutable children
        return MappingProxyType(
            {k: deep_freeze(v) for k, v in dict(value).items()}
        )
    return value
