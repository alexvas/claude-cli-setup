"""Semantic-source tests: reject selected version/revision/URL/digest
defaults outside ``docker-constructor.toml``.

The allowlist-driven scan extracts every concrete value from the
canonical inventory and reports any path-qualified duplicate found in
production semantic sources (Dockerfile, Compose, shell scripts,
documentation, etc.).  Test fixtures, generated inventory, and
OpenSpec artifacts are excluded.
"""
from __future__ import annotations

import pathlib
import re
import unittest

from docker.versioning.inventory import load_inventory

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _select_versions(inv):
    """Return a set of concrete values that must not appear elsewhere."""
    values = set()

    # Node base image digest
    values.add(inv.stages.base.node.digest)
    # tag is free-form but we catch it too
    values.add(inv.stages.base.node.tag)

    # Rust
    values.add(inv.stages.toolchain.rust.version)

    # uv
    values.add(inv.stages.toolchain.uv.version)
    for arch_entry in inv.stages.toolchain.uv.artifacts.values():
        values.add(arch_entry.url)
        values.add(arch_entry.sha256)

    # Python
    values.add(inv.stages.toolchain.python.version)

    # ty
    values.add(inv.stages.toolchain.ty.version)
    # "ty" is too short for substring scan — only check exact version

    # rtk
    values.add(inv.stages.rtk_prebuilt.rtk.version)
    for arch_entry in inv.stages.rtk_prebuilt.rtk.artifacts.values():
        values.add(arch_entry.url)
        values.add(arch_entry.sha256)

    # fd
    values.add(inv.stages.fd_prebuilt.fd.version)
    for arch_entry in inv.stages.fd_prebuilt.fd.artifacts.values():
        values.add(arch_entry.url)
        values.add(arch_entry.sha256)

    # Pi / OpenSpec
    values.add(inv.stages.pi_tools.pi.version)
    values.add(inv.stages.pi_tools.pi.source.package)
    values.add(inv.stages.openspec_tools.openspec.version)
    values.add(inv.stages.openspec_tools.openspec.source.package)

    # oh-my-zsh
    values.add(inv.stages.runtime.oh_my_zsh.revision)

    # Pi extensions
    for entry in inv.runtime_pi_extensions.values():
        values.add(entry.source.package)
        values.add(entry.version)

    return values


# Paths to scan (relative to repo root)
_SEMANTIC_SOURCES = [
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.runtime.yml",
    "docker/setup-python.sh",
    "docker/setup-zsh.sh",
    "docker/verify-runtime.sh",
    "docker/install-pi-extensions.sh",
    ".env.example",
    "README.md",
    "README.en.md",
    "README.zh.md",
    "docker/build_wrapper.py",
    "docker/versioning/rendering.py",
]

# Paths excluded from scanning
_SCAN_EXCLUDES = {
    "tests/",
    "openspec/changes/",
    "openspec/specs/",
    ".docker-generated/",
    ".git/",
    "docker-constructor.toml",
}

# Values that are acceptable in documentation files (describe system
# behavior, not suggest direct builds)
_DOC_ALLOWED = frozenset({
    "@arcanemachine/pi-read",
    "@llblab/pi-codex-usage",
    "pi-proxy",
    "3.14.6",  # default version mentioned in docs
    "0.80.10", "0.80.9",  # override examples in BuildKit section
    "1.6.0",  # override example
})

# Package identities used in the Dockerfile as npm install targets —
# the VERSION comes from the resolver; the package name is a constant
# identifier, not a version value.
_DOCKERFILE_PACKAGE_ALLOWED = frozenset({
    "@earendil-works/pi-coding-agent",
    "@fission-ai/openspec",
})

# Short literals that happen to match version numbers but are not
# toolchain versions (e.g. minimum compose version, Python version in
# a diagnostic message)
_ALLOWED_IN_CONTEXT = frozenset({
    "3.14.6",  # appears in override policy diagnostic; allowed
})

# Minimum length for substring scan (shorter values use word-boundary regex)
_MIN_SUBSTR_LEN = 8


def _value_found_in_line(value: str, line: str) -> bool:
    """Check if *value* appears in *line* as a meaningful literal.

    Short values (package names, versions) use ``\b`` word-boundary
    matching to avoid false positives (e.g. "ty" inside "empty").
    Long values (digests, URLs, SHA-256) use simple substring matching.
    """
    if len(value) >= _MIN_SUBSTR_LEN:
        return value in line
    # Word-boundary match: value must be surrounded by non-word chars
    # (whitespace, quotes, punctuation, start/end of line)
    return bool(re.search(r'(?<![\w.])' + re.escape(value) + r'(?![\w.])', line))


def _is_excluded(rel: str) -> bool:
    """True if *rel* matches an excluded prefix."""
    for prefix in _SCAN_EXCLUDES:
        if rel.startswith(prefix):
            return True
    # Also exclude exact match on docker-constructor.toml
    return rel == "docker-constructor.toml"


class TestSemanticSources(unittest.TestCase):
    """Inventory-aware duplicate-constant checks."""

    @classmethod
    def setUpClass(cls):
        inv_path = REPO_ROOT / "docker-constructor.toml"
        cls.inventory = load_inventory(inv_path)
        cls.forbidden = _select_versions(cls.inventory)
        cls.source_files = [
            p for p in _SEMANTIC_SOURCES
            if (REPO_ROOT / p).is_file()
        ]

    def test_no_duplicate_versions_in_semantic_sources(self):
        """No selected version/revision/URL/digest outside docker-constructor.toml."""
        violations = []
        for source_rel in self.source_files:
            path = REPO_ROOT / source_rel
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                for value in self.forbidden:
                    if not _value_found_in_line(value, line):
                        continue
                    # Package names referenced in documentation are not
                    # duplicate version data — they describe system behavior
                    if value in _DOC_ALLOWED and source_rel in (
                        "README.md", "README.en.md", "README.zh.md"
                    ):
                        continue
                    # Package names in Dockerfile npm install targets
                    # are constant identifiers, not version values
                    if value in _DOCKERFILE_PACKAGE_ALLOWED and source_rel == "Dockerfile":
                        continue
                    # Skip allowed-in-context values
                    if value in _ALLOWED_IN_CONTEXT and source_rel != "docker-constructor.toml":
                        # Only suppress for known diagnostic messages
                        # (the override policy minimum is surfaced as a
                        # diagnostic — not a build selection)
                        if "ge" in line and "3.14.6" in line:
                            continue
                    violations.append(
                        f"{source_rel}:{lineno} duplicates {value}"
                    )
        if violations:
            self.fail("\n".join(violations))

    # ------------------------------------------------------------------
    # Structural checks
    # ------------------------------------------------------------------

    def test_dockerfile_no_value_assignments_for_version_args(self):
        """Dockerfile ARG declarations are value-free for version inputs."""
        path = REPO_ROOT / "Dockerfile"
        content = path.read_text()
        version_arg_pattern = re.compile(
            r'^ARG\s+(NODE_BASE_IMAGE|RUST_VERSION|RUST_PROFILE|'
            r'RUST_COMPONENTS|UV_VERSION|UV_URL|UV_SHA256|'
            r'PYTHON_VERSION|TY_VERSION|'
            r'RTK_VERSION|RTK_URL|RTK_SHA256|'
            r'FD_VERSION|FD_URL|FD_SHA256|'
            r'PI_VERSION|OPENSPEC_VERSION|OH_MY_ZSH_VERSION|'
            r'EFFECTIVE_VERSIONS_FILE|RUSTUP_URL|RUSTUP_SHA256)\s*=',
            re.MULTILINE,
        )
        matches = version_arg_pattern.findall(content)
        if matches:
            self.fail(
                "Dockerfile contains version ARG with default value: "
                + ", ".join(matches)
            )

    def test_dockerfile_no_floating_from_node(self):
        """No floating FROM node:... only FROM ${NODE_BASE_IMAGE}."""
        path = REPO_ROOT / "Dockerfile"
        content = path.read_text()
        # Floating FROM node:... would look like "FROM node:24..." or
        # "FROM node:" without ${}
        if re.search(r'^FROM\s+node:', content, re.MULTILINE):
            self.fail("Dockerfile contains floating FROM node:... (use ${NODE_BASE_IMAGE})")

    def test_dockerfile_no_constructed_artifact_urls(self):
        """Dockerfile must not construct artifact URLs from separate version
        parts — use ${UV_URL}, ${RTK_URL}, ${FD_URL} directly."""
        path = REPO_ROOT / "Dockerfile"
        content = path.read_text()
        # Patterns like VERSION_NO_V="${FD_VERSION#v}" + URL construction
        if 'VERSION_NO_V=' in content:
            self.fail("Dockerfile constructs artifact URLs (uses VERSION_NO_V)")

    def test_compose_no_concrete_fallbacks(self):
        """Compose build args must use :? (required) not :- (default)
        for selected version inputs."""
        path = REPO_ROOT / "docker-compose.yml"
        content = path.read_text()
        forbidden_pattern = re.compile(
            r'\$\{(NODE_BASE_IMAGE|RUST_VERSION|RUST_PROFILE|'
            r'RUST_COMPONENTS|UV_VERSION|UV_URL|UV_SHA256|'
            r'PYTHON_VERSION|TY_VERSION|'
            r'RTK_VERSION|RTK_URL|RTK_SHA256|'
            r'FD_VERSION|FD_URL|FD_SHA256|'
            r'PI_VERSION|OPENSPEC_VERSION|OH_MY_ZSH_VERSION|'
            r'EFFECTIVE_VERSIONS_FILE):-'
        )
        matches = forbidden_pattern.findall(content)
        if matches:
            self.fail("Compose has :- defaults for version inputs: " + ", ".join(matches))

    def test_dot_env_example_no_selected_versions(self):
        """``.env.example`` must not contain selected versions/revisions."""
        path = REPO_ROOT / ".env.example"
        content = path.read_text()
        for value in self.forbidden:
            if value in content:
                self.fail(f".env.example contains {value}")

    def test_setup_python_no_version_fallback(self):
        """setup-python.sh must not contain version fallbacks."""
        path = REPO_ROOT / "docker/setup-python.sh"
        content = path.read_text()
        # No dpkg --compare-versions with concrete minimum from inventory
        for value in self.forbidden:
            if value in content:
                self.fail(f"setup-python.sh contains {value}")

    def test_install_pi_extensions_no_package_identities(self):
        """install-pi-extensions.sh must not contain hard-coded
        package identities."""
        path = REPO_ROOT / "docker/install-pi-extensions.sh"
        content = path.read_text()
        for entry in self.inventory.runtime_pi_extensions.values():
            pkg = entry.source.package
            if pkg in content:
                self.fail(
                    f"install-pi-extensions.sh contains package {pkg}"
                )

    def test_verify_runtime_no_concrete_versions(self):
        """verify-runtime.sh must not contain concrete expected versions."""
        path = REPO_ROOT / "docker/verify-runtime.sh"
        content = path.read_text()
        # These are the pre-migration concrete values from the inventory
        for value in self.forbidden:
            if value in content:
                self.fail(f"verify-runtime.sh contains {value}")

    def test_documentation_no_direct_build_defaults(self):
        """README files must not suggest direct build with version
        environment defaults (e.g. PYTHON_VERSION=... docker compose build)."""
        doc_pattern = re.compile(
            r'(PYTHON_VERSION|PI_VERSION|OPENSPEC_VERSION)=[0-9]'
        )
        for readme in ["README.md", "README.en.md", "README.zh.md"]:
            path = REPO_ROOT / readme
            content = path.read_text()
            if doc_pattern.search(content):
                self.fail(f"{readme} contains direct-build version defaults")

    def test_readmes_use_resolver_compose(self):
        """README files must route all compose commands through the resolver
        (versions.py compose), never via raw docker compose build/run/config.

        Descriptive text about launch-pi.py is exempt — only code-fence
        commands and standalone inline commands are flagged."""
        _cmd = re.compile(r'^\s*docker\s+compose\s+(build|run|config)\b')
        violations: list[str] = []
        for readme in ["README.md", "README.en.md", "README.zh.md"]:
            path = REPO_ROOT / readme
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if not _cmd.search(stripped):
                    continue
                # Exempt descriptive text (lines containing launch-pi or
                # requirement statements about Docker Compose itself)
                if "launch-pi" in stripped.lower():
                    continue
                if stripped.startswith("- Docker Compose"):
                    continue
                violations.append(f"{readme}:{lineno}: {stripped}")
        if violations:
            self.fail(
                "README files contain raw docker compose commands that bypass "
                "the resolver — replace with ./docker/versions.py compose:\n"
                + "\n".join(violations)
            )


# ---------------------------------------------------------------------------
# Stale-reference contract — Task 3.2
# ---------------------------------------------------------------------------

# Files maintained by the project — any ``versions.toml`` reference in
# these is a defect unless explicitly excluded below.
_STALE_SCAN_ROOTS = [
    "README.md",
    "README.en.md",
    "README.zh.md",
    "docker/",
    "tests/",
    "openspec/changes/",
    "openspec/specs/",
    ".env.example",
]

# Whole-file exclusions — files that are completely skipped.
# Prefer narrow block-level exclusions below; use whole-file only for
# files that are entirely self-describing the legacy name.
_STALE_EXCLUDED_FILES = frozenset({
    # Archived OpenSpec history — immutable record of past decisions
    "openspec/changes/archive/",
    # This very test file — self-referencing docstrings and
    # assertions that name the legacy file being scanned for
    "tests/test_version_semantic_sources.py",
})

# Block-level allowlists: map of file → set of (start_line, end_line)
# ranges where ``versions.toml`` references are intentionally allowed.
# Ranges are 1-indexed and inclusive.
_STALE_BLOCK_ALLOWLIST: dict[str, set[tuple[int, int]]] = {
    "tests/test_version_rendering.py": {
        # Arbitrary temp fixture filenames in TestWriteEffectiveInventory
        # (write/read-back/determinism/atomic tests)
        (219, 308),
        # Absolute path and traversal rejection tests — path names are
        # arbitrary, not authoritative
        (335, 360),
    },
    "tests/test_versions_cli.py": {
        # TestInventoryDiscovery — intentionally references the legacy
        # name to test no-fallback behavior (Task 1.1/1.2)
        (692, 815),
    },
}

# Paths excluded by prefix — any file whose path starts with one of
# these is skipped entirely.
_STALE_EXCLUDED_PREFIXES = tuple(_STALE_EXCLUDED_FILES)

# Additional line-level allowlist: entire files that mention
# ``versions.toml`` in a benign context (e.g. this very contract,
# changelogs, migration notes in active changes describing the rename).
_STALE_LINE_ALLOWLIST = frozenset({
    # The rename change itself documents the old name
    "openspec/changes/rename-version-inventory",
})


class TestStaleVersionTomlReferences(unittest.TestCase):
    """No maintained file may reference ``versions.toml`` except for
    archived history, intentionally arbitrary fixtures, and the rename
    change that documents the migration."""

    _STALE_PATTERN = re.compile(r"\bversions\.toml\b")
    _NEGATIVE_PATTERN = re.compile(
        r"SHALL\s+(?:NOT\s+|reject\b)", re.IGNORECASE
    )

    def _scan_files(self) -> list[pathlib.Path]:
        """Yield every file under scan roots that exists."""
        files: list[pathlib.Path] = []
        for root_spec in _STALE_SCAN_ROOTS:
            root = REPO_ROOT / root_spec
            if root.is_dir():
                for p in root.rglob("*"):
                    if p.is_file():
                        files.append(p)
            elif root.is_file():
                files.append(root)
        return files

    @staticmethod
    def _is_excluded(rel: str) -> bool:
        """True if *rel* should be skipped by the stale-reference scan."""
        for prefix in _STALE_EXCLUDED_PREFIXES:
            if rel.startswith(prefix):
                return True
        return False

    @staticmethod
    def _is_line_allowlisted(rel: str) -> bool:
        """True if *rel* is in a file where ``versions.toml`` mentions
        are contextually allowed (e.g. rename documentation)."""
        for prefix in _STALE_LINE_ALLOWLIST:
            if rel.startswith(prefix):
                return True
        return False

    @staticmethod
    def _is_in_allowlisted_block(rel: str, lineno: int) -> bool:
        """True if *lineno* falls within an allowlisted range for *rel*."""
        ranges = _STALE_BLOCK_ALLOWLIST.get(rel)
        if ranges is None:
            return False
        return any(lo <= lineno <= hi for (lo, hi) in ranges)

    def test_no_stale_versions_toml_references(self):
        """Scan maintained files for ``versions.toml`` references.

        Every hit must be classified as archived history, fixture data,
        an allowlisted block, or a documented rename artifact —
        otherwise it is a defect."""
        violations: list[str] = []
        for path in self._scan_files():
            rel = str(path.relative_to(REPO_ROOT))
            if self._is_excluded(rel):
                continue
            allowlisted = self._is_line_allowlisted(rel)
            try:
                for lineno, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if not self._STALE_PATTERN.search(line):
                        continue
                    # Negative clauses (SHALL NOT fall back, SHALL reject) are
                    # intentional and describe the contract being enforced here.
                    if self._NEGATIVE_PATTERN.search(line):
                        continue
                    if allowlisted:
                        continue
                    if self._is_in_allowlisted_block(rel, lineno):
                        continue
                    violations.append(f"{rel}:{lineno}: {line.strip()[:100]}")
            except UnicodeDecodeError:
                # Binary files — skip
                pass
        if violations:
            self.fail(
                "Maintained files contain stale references to "
                "versions.toml — rename to docker-constructor.toml, "
                "add an exclusion, or classify as fixture/archive:\n"
                + "\n".join(violations)
            )
