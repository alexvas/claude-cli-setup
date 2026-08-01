"""Migration contract tests — reject stale references to removed surface.

Stage 13 replaces old CLIs, wrappers, Compose fragments, generated
artifacts, inf-splitter settings, and separate phase inventories with
the single ``docker/docker-constructor.py`` facade.  These RED tests
document the removal contract: every scan MUST fail until the
referenced files and documentation are updated in 13.3–13.5.
"""
from __future__ import annotations

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent

# ════════════════════════════════════════════════════════════════════
# Shell script scan roots
# ════════════════════════════════════════════════════════════════════

_SH_SCAN_ROOTS: list[str] = [
    "docker/",
]

# Shell scripts excluded entirely
_SH_EXCLUDED_FILES = frozenset({
    # This file delegates to build_wrapper (being removed in 13.4)
    "docker/apply-rootless-port-forward.sh",
})

# ════════════════════════════════════════════════════════════════════
# Documentation scan (beyond root READMEs)
# ════════════════════════════════════════════════════════════════════

_DOC_SCAN_ROOTS: list[str] = [
    "docker/",
]

# Main OpenSpec specs — authoritative, maintained documentation.
# The current change's delta specs (openspec/changes/<name>/) are
# excluded because they intentionally describe the migration.
_OPENSPEC_SPECS_DIR: str = "openspec/specs/"
_OPENSPEC_CHANGES_DIR: str = "openspec/changes/"

_DOC_FILE_EXCLUDED = frozenset({
    # Historical acceptance evidence
    "docker/verify_stage_6/",
})

# ════════════════════════════════════════════════════════════════════
# Configuration file scan (only maintained TOML)
# ════════════════════════════════════════════════════════════════════

# Compose YAML files are removed in 13.4 and are excluded.  Only the
# reviewed inventory and env template are maintained.
_CFG_SCAN_FILES: tuple[str, ...] = (
    "docker-constructor.toml",
    ".env.example",
)

# ════════════════════════════════════════════════════════════════════
# Python scan roots
# ════════════════════════════════════════════════════════════════════

_PY_SCAN_ROOTS = [
    "docker/",
    "tests/",
]

# Files are excluded **in their entirety**
_PY_EXCLUDED = {
    # Still being removed in later 13.x tasks
    "docker/build_wrapper.py",
    "docker/gen-models-json.py",
    "docker/versioning/cli.py",
    "launch-pi.py",
    # Historical acceptance evidence
    "docker/verify_stage_6/",
}

# Files with line-level allowlists (contextual mentions)
_PY_LINE_ALLOWLIST = frozenset({
    # Docstring-only mention of what was extracted from
    "docker/tui.py",
    # Installer docstring describing what NOT to depend on
    "docker/runtime_installer.py",
    # This very test file documents the contract
    "tests/test_constructor_migration_contract.py",
    # OpenSpec artifacts describing the change
    "openspec/",
    # Runtime verification correctly asserts these paths must NOT exist
    "docker/versioning/runtime_verification.py",
    "tests/test_constructor_runtime_verification.py",
})

# Entire files excluded from the forbidden-runtime-paths scan because
# they document the absence contract (assert paths must not exist) or
# are legacy acceptance evidence.
_FORBIDDEN_PATHS_EXCLUDED_FILES = frozenset({
    "docker/versioning/runtime_verification.py",
    "tests/test_constructor_runtime_verification.py",
    "tests/test_version_source_contracts.py",
    "tests/test_versioned_image_acceptance.py",
})


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _py_files() -> dict[str, pathlib.Path]:
    """Return ``{relpath: abspath}`` for every production Python file
    under scan roots, excluding whole-file exclusions."""
    result: dict[str, pathlib.Path] = {}
    for root_spec in _PY_SCAN_ROOTS:
        root = REPO / root_spec
        if root.is_dir():
            for p in root.rglob("*.py"):
                if p.is_file():
                    rel = str(p.relative_to(REPO))
                    if any(rel.startswith(ex) for ex in _PY_EXCLUDED):
                        continue
                    result[rel] = p
        elif root.is_file():
            rel = str(root.relative_to(REPO))
            if not any(rel.startswith(ex) for ex in _PY_EXCLUDED):
                result[rel] = root
    return result


def _lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """Read *path* lines, returning ``[(lineno, text), …]``."""
    try:
        return list(
            enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        )
    except UnicodeDecodeError:
        return []


# ════════════════════════════════════════════════════════════════════
# 13.1a — Old CLI surface
# ════════════════════════════════════════════════════════════════════

_OLD_CLI_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "versions.py used as user-facing command",
        re.compile(r"versions\.py\s+(compose|validate|check-updates|env|show|run)"),
    ),
    (
        "launch-pi.py reference",
        re.compile(r"launch-pi\.py"),
    ),
    (
        "build_wrapper.py reference",
        re.compile(r"build_wrapper\.py"),
    ),
    (
        "gen-models-json reference",
        re.compile(r"gen-models-json"),
    ),
]


class TestNoStaleCLIReferences(unittest.TestCase):
    """Production Python files MUST NOT reference old CLI entry points
    or wrappers that are being removed in Stage 13."""

    def test_no_stale_cli_references_in_docker_py(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_py_files().items()):
            allowlisted = rel in _PY_LINE_ALLOWLIST
            for lineno, line in _lines(path):
                for label, pat in _OLD_CLI_PATTERNS:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — {line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Production files reference old CLI surface — update to "
                "docker/docker-constructor.py or remove:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1b — Compose surface
# ════════════════════════════════════════════════════════════════════

_COMPOSE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "COMPOSE_FILE env var",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "docker-compose.yml reference",
        re.compile(r"docker-compose(?:\\.runtime)?\\.yml"),
    ),
    (
        "compose as subcommand",
        re.compile(r"versions\\.py\\s+compose"),
    ),
]

# Generated Compose fragment patterns — project-specific or temporary
# override files the old launcher created.
_GENERATED_FRAGMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "compose.projN.yml fragment",
        re.compile(r"compose\\.proj\\d+\\.yml"),
    ),
    (
        ".projN.yml hidden fragment",
        re.compile(r"\\.proj\\d+\\.yml"),
    ),
    (
        "generate_proj_fragment call",
        re.compile(r"generate_proj_fragment"),
    ),
    (
        "extra_fragments list",
        re.compile(r"extra_fragments"),
    ),
    (
        ".override.yml hidden fragment",
        re.compile(r"\\.override\\.yml"),
    ),
]


class TestNoStaleComposeReferences(unittest.TestCase):
    """Production Python files MUST NOT reference Compose files,
    ``COMPOSE_FILE``, or ``versions.py compose``."""

    def test_no_stale_compose_references_in_docker_py(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_py_files().items()):
            allowlisted = rel in _PY_LINE_ALLOWLIST
            for lineno, line in _lines(path):
                for label, pat in _COMPOSE_PATTERNS + _GENERATED_FRAGMENT_PATTERNS:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — {line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Production files reference Compose or generated fragments — "
                "replace with direct Docker rendering:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1c — Inf-splitter settings
# ════════════════════════════════════════════════════════════════════

_INF_SPLITTER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "inf-splitter.toml path",
        re.compile(r"inf-splitter\.toml"),
    ),
    (
        "/etc/inf-splitter path",
        re.compile(r"/etc/inf-splitter"),
    ),
    (
        "inf-splitter provider key",
        re.compile(r'"inf-splitter"'),
    ),
]


class TestNoStaleInfSplitterReferences(unittest.TestCase):
    """Production files MUST NOT reference ``/etc/inf-splitter/``,
    ``inf-splitter.toml``, or the ``inf-splitter`` provider key."""

    def test_no_stale_inf_splitter_references(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_py_files().items()):
            allowlisted = rel in _PY_LINE_ALLOWLIST
            for lineno, line in _lines(path):
                for label, pat in _INF_SPLITTER_PATTERNS:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — {line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Production files reference inf-splitter — remove or "
                "migrate to docker-constructor model:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1d — Unified inventory (single source of truth)
# ════════════════════════════════════════════════════════════════════

_SEPARATE_INVENTORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "versions.toml (pre-rename inventory)",
        re.compile(r"\bversions\.toml\b"),
    ),
    (
        "separate build inventory mention",
        re.compile(r"\bbuild[-_]inventory\.toml\b"),
    ),
    (
        "separate runtime inventory mention",
        re.compile(r"\bruntime[-_]inventory\.toml\b"),
    ),
]


class TestNoSeparatePhaseInventories(unittest.TestCase):
    """Production files MUST reference exactly one
    ``docker-constructor.toml`` as the reviewed inventory — never
    separate per-phase TOML files."""

    def test_no_separate_inventory_references(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_py_files().items()):
            allowlisted = rel in _PY_LINE_ALLOWLIST
            for lineno, line in _lines(path):
                for label, pat in _SEPARATE_INVENTORY_PATTERNS:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — {line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Production files reference separate phase inventories — "
                "use docker-constructor.toml as the single source:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1e — Forbidden runtime configuration paths
# ════════════════════════════════════════════════════════════════════

# Paths inside the container that MUST NOT be referenced as readable
# or mounted from host-side reviewed/build artifacts.
_FORBIDDEN_CONTAINER_PATHS: list[tuple[str, re.Pattern[str]]] = [
    (
        "docker-constructor.toml mounted in container",
        re.compile(r"/run/pi-cli/docker-constructor\.toml"),
    ),
    (
        "build effective projection mounted in container",
        re.compile(r"/run/pi-cli/docker-constructor\.build\.effective\.toml"),
    ),
    (
        "host-side reviewed source reachable at runtime",
        re.compile(r"/usr/local/share/pi-cli/docker-constructor\.toml"),
    ),
]


class TestNoForbiddenRuntimeConfigurationPaths(unittest.TestCase):
    """Production files MUST NOT mount or reference reviewed inventory
    or build projections as readable inside the runtime container."""

    def test_no_forbidden_runtime_paths(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_py_files().items()):
            # These files correctly document/assert the absence contract
            if rel in _FORBIDDEN_PATHS_EXCLUDED_FILES:
                continue
            allowlisted = rel in _PY_LINE_ALLOWLIST
            # Also allow OpenSpec specs that describe what SHALL NOT happen
            if rel.startswith("openspec/"):
                continue
            for lineno, line in _lines(path):
                for label, pat in _FORBIDDEN_CONTAINER_PATHS:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — {line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Production files reference forbidden runtime paths — "
                "these files MUST NOT be accessible inside the container:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1f — Documentation references
# ════════════════════════════════════════════════════════════════════

_DOC_FILES: tuple[str, ...] = (
    "README.md",
    "README.en.md",
    "README.zh.md",
)

_DOC_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "launch-pi.py reference in docs",
        re.compile(r"\./launch-pi\.py|python3\s+launch-pi\.py"),
    ),
    (
        "docker/versions.py compose in docs",
        re.compile(r"\./docker/versions\.py\s+compose"),
    ),
    (
        "docker/versions.py validate in docs",
        re.compile(r"\./docker/versions\.py\s+validate"),
    ),
    (
        "docker/versions.py env in docs",
        re.compile(r"\./docker/versions\.py\s+env"),
    ),
    (
        "docker/versions.py check-updates in docs",
        re.compile(r"\./docker/versions\.py\s+check-updates"),
    ),
    (
        "docker/versions.py show in docs",
        re.compile(r"\./docker/versions\.py\s+show"),
    ),
    (
        "build_wrapper.py in docs",
        re.compile(r"docker/build_wrapper\.py"),
    ),
    (
        "docker-compose in docs",
        re.compile(r"docker-compose(?:\.runtime)?\.yml"),
    ),
    (
        "COMPOSE_FILE in docs",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "generated compose fragment in docs",
        re.compile(r"compose\.proj\d+\.yml"),
    ),
    (
        "versus additional projects limit in docs",
        re.compile(r"(?:до\s+двух|up to two)\s+(?:дополнительных\s+)?проектов"),
    ),
    (
        "two additional projects limit in docs",
        re.compile(r"two (?:additional )?projects"),
    ),
]


class TestNoStaleDocumentationReferences(unittest.TestCase):
    """READMEs MUST reference ``docker/docker-constructor.py`` commands,
    not ``versions.py``, ``launch-pi.py``, ``build_wrapper.py``, or
    Compose files."""

    def test_no_stale_references_in_readmes(self) -> None:
        violations: list[str] = []
        for doc_name in _DOC_FILES:
            doc_path = REPO / doc_name
            if not doc_path.is_file():
                continue
            for lineno, line in _lines(doc_path):
                for label, pat in _DOC_FORBIDDEN:
                    m = pat.search(line)
                    if not m:
                        continue
                    violations.append(
                        f"{doc_name}:{lineno}: {label} — "
                        f"{line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "README files reference removed or renamed commands — "
                "update to docker/docker-constructor.py interface:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1g — Shell script scan
# ════════════════════════════════════════════════════════════════════

_SH_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "build_wrapper.py in shell script",
        re.compile(r"build_wrapper\.py"),
    ),
    (
        "versions.py path in shell script",
        re.compile(r"versions\.py"),
    ),
    (
        "Compose in shell script",
        re.compile(r"\bCompose\b"),
    ),
    (
        "launch-pi.py in shell script",
        re.compile(r"launch-pi\.py"),
    ),
    (
        "docker-compose in shell script",
        re.compile(r"docker-compose"),
    ),
    (
        "COMPOSE_FILE in shell script",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "inf-splitter in shell script",
        re.compile(r"inf-splitter"),
    ),
    (
        "generated compose fragment in shell script",
        re.compile(r"compose\.proj\d+\.yml"),
    ),
]

# Shell scripts with contextual allowlist lines
_SH_LINE_ALLOWLIST = frozenset({
    # entrypoint.sh runs INSIDE the container — its PROJECT_PATH_*
    # comments document the launcher contract, not user-facing CLI.
    # Only flag if it references removed surface names.
    "docker/entrypoint.sh",
})


def _sh_files() -> dict[str, pathlib.Path]:
    """Return ``{relpath: abspath}`` for every shell script under
    scan roots, excluding whole-file exclusions."""
    result: dict[str, pathlib.Path] = {}
    for root_spec in _SH_SCAN_ROOTS:
        root = REPO / root_spec
        if not root.is_dir():
            continue
        for p in root.rglob("*.sh"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(REPO))
            if rel in _SH_EXCLUDED_FILES:
                continue
            result[rel] = p
    return result


class TestNoStaleShellScriptReferences(unittest.TestCase):
    """Shell scripts MUST NOT reference ``build_wrapper.py``,
    ``versions.py``, Compose, or ``launch-pi.py``."""

    def test_no_stale_references_in_shell_scripts(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_sh_files().items()):
            allowlisted = rel in _SH_LINE_ALLOWLIST
            for lineno, line in _lines(path):
                for label, pat in _SH_FORBIDDEN:
                    m = pat.search(line)
                    if not m:
                        continue
                    if allowlisted:
                        # Per-line judgement for entrypoint.sh:
                        # "Compose/launch-pi.py" and "Compose contract"
                        # are historical comments that must be updated.
                        pass
                    violations.append(
                        f"{rel}:{lineno}: {label} — "
                        f"{line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Shell scripts reference removed surface — update to "
                "docker/docker-constructor.py or remove obsolete files:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1h — Documentation beyond root READMEs
# ════════════════════════════════════════════════════════════════════

_NON_README_DOC_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "versions.py in maintained doc",
        re.compile(r"\./docker/versions\.py|python3\s+docker/versions\.py"),
    ),
    (
        "build_wrapper.py in maintained doc",
        re.compile(r"build_wrapper\.py"),
    ),
    (
        "launch-pi.py in maintained doc",
        re.compile(r"launch-pi\.py"),
    ),
    (
        "COMPOSE_FILE in maintained doc",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "docker-compose in maintained doc",
        re.compile(r"docker-compose"),
    ),
    (
        "inf-splitter in maintained doc",
        re.compile(r"inf-splitter"),
    ),
    (
        "generated compose fragment in maintained doc",
        re.compile(r"compose\.proj\d+\.yml"),
    ),
]


def _maintained_doc_files() -> dict[str, pathlib.Path]:
    """Return maintained ``.md`` files under ``docker/`` (not READMEs,
    not verify_stage_6/, not OpenSpec artifacts)."""
    result: dict[str, pathlib.Path] = {}
    for root_spec in _DOC_SCAN_ROOTS:
        root = REPO / root_spec
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(REPO))
            if any(rel.startswith(ex) for ex in _DOC_FILE_EXCLUDED):
                continue
            result[rel] = p
    return result


class TestNoStaleMaintainedDocReferences(unittest.TestCase):
    """Maintained documentation under ``docker/`` MUST NOT reference
    removed CLIs, Compose, or inf-splitter."""

    def test_no_stale_references_in_maintained_docs(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_maintained_doc_files().items()):
            for lineno, line in _lines(path):
                for label, pat in _NON_README_DOC_FORBIDDEN:
                    m = pat.search(line)
                    if not m:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — "
                        f"{line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Maintained documentation references removed surface:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1i — Main OpenSpec specs (authoritative maintained documentation)
# ════════════════════════════════════════════════════════════════════

_SPEC_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "versions.py as command in spec",
        re.compile(r"docker/versions\.py"),
    ),
    (
        "build_wrapper.py in spec",
        re.compile(r"docker/build_wrapper\.py"),
    ),
    (
        "launch-pi.py in spec",
        re.compile(r"launch-pi\.py"),
    ),
    (
        "inf-splitter in spec",
        re.compile(r"inf-splitter"),
    ),
    (
        "gen-models-json in spec",
        re.compile(r"gen-models-json"),
    ),
    (
        "docker-compose in spec",
        re.compile(r"docker-compose"),
    ),
    (
        "COMPOSE_FILE in spec",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "compose.proj in spec",
        re.compile(r"compose\.proj"),
    ),
    (
        "Compose service/service reference in spec",
        re.compile(r"Compose\s+(service|command|configuration|fragment)"),
    ),
]


def _main_spec_files() -> dict[str, pathlib.Path]:
    """Return maintained OpenSpec spec files (not change deltas)."""
    result: dict[str, pathlib.Path] = {}
    specs_dir = REPO / _OPENSPEC_SPECS_DIR
    if specs_dir.is_dir():
        for p in specs_dir.rglob("*.md"):
            if p.is_file():
                rel = str(p.relative_to(REPO))
                result[rel] = p
    return result


class TestNoStaleMainSpecReferences(unittest.TestCase):
    """Authoritative ``openspec/specs/`` MUST NOT reference removed
    CLIs, Compose, inf-splitter, or generated fragments."""

    def test_no_stale_references_in_main_specs(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_main_spec_files().items()):
            for lineno, line in _lines(path):
                for label, pat in _SPEC_FORBIDDEN:
                    m = pat.search(line)
                    if not m:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — "
                        f"{line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Main OpenSpec specs reference removed surface — "
                "update to docker/docker-constructor.py contract:\n"
                + "\n".join(violations)
            )


# ════════════════════════════════════════════════════════════════════
# 13.1j — Maintained configuration files
# ════════════════════════════════════════════════════════════════════

_CFG_FORBIDDEN: list[tuple[str, re.Pattern[str]]] = [
    (
        "versions.py in config",
        re.compile(r"versions\.py"),
    ),
    (
        "build_wrapper in config",
        re.compile(r"build_wrapper"),
    ),
    (
        "launch-pi in config",
        re.compile(r"launch-pi"),
    ),
    (
        "inf-splitter in config",
        re.compile(r"inf-splitter"),
    ),
    (
        "inf-splitter.toml path in config",
        re.compile(r"inf-splitter\.toml"),
    ),
    (
        "docker-compose in config",
        re.compile(r"docker-compose"),
    ),
    (
        "COMPOSE_FILE in config",
        re.compile(r"COMPOSE_FILE"),
    ),
    (
        "generated compose fragment in config",
        re.compile(r"compose\.proj\d+\.yml"),
    ),
    (
        "PROXY_PORT in config",
        re.compile(r"PROXY_PORT"),
    ),
]


def _cfg_files() -> dict[str, pathlib.Path]:
    """Return maintained configuration files (only reviewed inventory)."""
    result: dict[str, pathlib.Path] = {}
    for name in _CFG_SCAN_FILES:
        p = REPO / name
        if p.is_file():
            result[name] = p
    return result


class TestNoStaleConfigReferences(unittest.TestCase):
    """Maintained configuration files MUST NOT reference removed
    CLIs, Compose, or inf-splitter."""

    def test_no_stale_references_in_config_files(self) -> None:
        violations: list[str] = []
        for rel, path in sorted(_cfg_files().items()):
            for lineno, line in _lines(path):
                for label, pat in _CFG_FORBIDDEN:
                    m = pat.search(line)
                    if not m:
                        continue
                    violations.append(
                        f"{rel}:{lineno}: {label} — "
                        f"{line.strip()[:100]}"
                    )
        if violations:
            self.fail(
                "Maintained configuration files reference removed surface:\n"
                + "\n".join(violations)
            )
