"""Shared version values and ordering across providers.

Provides SemanticVersion (strict semver.org 2.0.0) for npm/PyPI/GitHub tags,
plus comparison helpers.  NumericVersion from constraints.py handles X.Y.Z
ordering independently.

No Docker, no network, no subprocess.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Semver regex — strict semver.org 2.0.0
# matches: 1.2.3, 0.1.0, 1.0.0-alpha, 1.0.0-alpha.1, 1.0.0+build
# rejects: 1.2.3-01 (leading zero in prerelease numeric), 1.2.3-!!!
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(
    r"""
    ^
    (0|[1-9]\d*)                 # major
    \.
    (0|[1-9]\d*)                 # minor
    \.
    (0|[1-9]\d*)                 # patch
    (?:
        -                       # prerelease hyphen
        (
            (?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)
            (?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*
        )
    )?
    (?:
        \+                       # build plus
        (
            [0-9a-zA-Z-]+
            (?:\.[0-9a-zA-Z-]+)*
        )
    )?
    $
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# SemanticVersion
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=False)
class SemanticVersion:
    """Strict semver.org 2.0.0 version.

    Ordering follows semver precedence:
    - numeric identifiers compare numerically
    - numeric prerelease identifier is lower than non-numeric
    - stable (no prerelease) is higher than any prerelease
    - build metadata does not affect ordering
    - leading zero in numeric prerelease is invalid (caught at parse time)
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += "-" + ".".join(self.prerelease)
        if self.build:
            base += "+" + ".".join(self.build)
        return base

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    @property
    def is_stable(self) -> bool:
        return not self.prerelease

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch
        # Prerelease: stable > any prerelease
        if not self.prerelease and other.prerelease:
            return False  # self is stable, other is prerelease → self > other
        if self.prerelease and not other.prerelease:
            return True  # self is prerelease, other is stable → self < other
        if not self.prerelease and not other.prerelease:
            return False  # equal components, both stable
        # Both have prerelease: compare identifiers pairwise
        return _compare_prerelease(self.prerelease, other.prerelease) < 0

    def __le__(self, other: object) -> bool:
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return other < self

    def __ge__(self, other: object) -> bool:
        return self == other or self > other

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))


def _compare_prerelease(
    a: tuple[str, ...], b: tuple[str, ...]
) -> int:
    """Compare two prerelease identifier tuples per semver.org precedence.

    Returns negative if a < b, 0 if equal, positive if a > b.
    """
    for pa, pb in zip(a, b):
        result = _compare_prerelease_identifier(pa, pb)
        if result != 0:
            return result
    # Shorter loses (fewer identifiers = lower version) — consistent with
    # semver.org: "A larger set of pre-release fields has a higher
    # precedence than a smaller set, if all the preceding identifiers are
    # equal."
    if len(a) < len(b):
        return -1  # a has fewer → a < b
    if len(a) > len(b):
        return 1  # a has more → a > b
    return 0


def _compare_prerelease_identifier(a: str, b: str) -> int:
    """Compare two prerelease identifiers per semver.org rules.

    - Both numeric: compare numerically
    - One numeric, one non-numeric: numeric sorts lower
    - Both non-numeric: compare lexically
    """
    a_int = _try_int(a)
    b_int = _try_int(b)
    if a_int is not None and b_int is not None:
        if a_int < b_int:
            return -1
        if a_int > b_int:
            return 1
        return 0
    if a_int is not None:
        return -1  # numeric sorts before non-numeric
    if b_int is not None:
        return 1
    # Both non-numeric: lexical
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _try_int(s: str) -> Optional[int]:
    """Return int(s) if s consists entirely of digits, None otherwise."""
    if s.isdigit():
        return int(s)
    return None


def parse_semver(raw: str) -> SemanticVersion:
    """Parse a strict semver string.

    Raises ValueError for invalid versions (malformed, leading zeros, etc.).
    """
    m = _SEMVER_RE.match(raw.strip())
    if not m:
        raise ValueError(f"Invalid semver: {raw!r}")

    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3))

    prerelease_str = m.group(4)
    prerelease = tuple(prerelease_str.split(".")) if prerelease_str else ()

    build_str = m.group(5)
    build = tuple(build_str.split(".")) if build_str else ()

    return SemanticVersion(
        major=major, minor=minor, patch=patch,
        prerelease=prerelease, build=build,
    )
