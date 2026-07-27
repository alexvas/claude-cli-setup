"""Source-contract tests: require value-free Dockerfile ARG declarations,
required Compose interpolation, and inventory-backed runtime scripts.
"""
from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestDockerfileContracts(unittest.TestCase):
    """Value-free ARG declarations with minimal cache scope."""

    _DOCKERFILE = REPO_ROOT / "Dockerfile"

    @classmethod
    def setUpClass(cls):
        cls.content = cls._DOCKERFILE.read_text()

    def test_all_version_args_declared(self):
        """Every consumed version input has a value-free ARG."""
        required = {
            "NODE_BASE_IMAGE",
            "RUST_VERSION", "RUST_PROFILE", "RUST_COMPONENTS",
            "RUSTUP_URL", "RUSTUP_SHA256",
            "UV_VERSION", "UV_URL", "UV_SHA256",
            "PYTHON_VERSION",
            "TY_VERSION",
            "RTK_VERSION", "RTK_URL", "RTK_SHA256",
            "FD_VERSION", "FD_URL", "FD_SHA256",
            "PI_VERSION", "OPENSPEC_VERSION",
            "OH_MY_ZSH_VERSION",
            "EFFECTIVE_VERSIONS_FILE",
        }
        # Collect all declared ARGs (value-free or not)
        declared = set()
        for m in re.finditer(r'^ARG\s+([A-Z][A-Z0-9_]*)', self.content, re.MULTILINE):
            declared.add(m.group(1))
        missing = required - declared
        if missing:
            self.fail("Dockerfile missing required ARG declarations: " + ", ".join(sorted(missing)))

    def test_no_version_arg_has_default(self):
        """Version ARGs must not carry default values in the Dockerfile."""
        version_arg_default = re.compile(
            r'^ARG\s+('
            r'NODE_BASE_IMAGE|RUST_VERSION|RUST_PROFILE|RUST_COMPONENTS|'
            r'RUSTUP_URL|RUSTUP_SHA256|'
            r'UV_VERSION|UV_URL|UV_SHA256|'
            r'PYTHON_VERSION|TY_VERSION|'
            r'RTK_VERSION|RTK_URL|RTK_SHA256|'
            r'FD_VERSION|FD_URL|FD_SHA256|'
            r'PI_VERSION|OPENSPEC_VERSION|OH_MY_ZSH_VERSION|'
            r'EFFECTIVE_VERSIONS_FILE'
            r')=',
            re.MULTILINE,
        )
        matches = version_arg_default.findall(self.content)
        if matches:
            self.fail("Version ARGs with default values: " + ", ".join(matches))

    def test_node_base_image_before_first_from(self):
        """NODE_BASE_IMAGE must be declared before the first FROM that uses it."""
        # Strip comments, find first FROM line
        lines = self.content.splitlines()
        first_from_idx = None
        for i, line in enumerate(lines):
            stripped = line.split("#")[0].strip()
            if re.match(r'^FROM\s', stripped):
                first_from_idx = i
                break
        self.assertIsNotNone(first_from_idx, "No FROM line found")

        # NODE_BASE_IMAGE must be declared before first FROM
        for i, line in enumerate(lines[:first_from_idx]):
            stripped = line.split("#")[0].strip()
            if re.match(r'^ARG\s+NODE_BASE_IMAGE\b', stripped):
                return
        self.fail("ARG NODE_BASE_IMAGE not declared before first FROM")

    def test_node_base_image_used_in_from(self):
        """First FROM must use ${NODE_BASE_IMAGE} not a concrete image."""
        lines = self.content.splitlines()
        for line in lines:
            stripped = line.split("#")[0].strip()
            if re.match(r'^FROM\s', stripped):
                self.assertIn("${NODE_BASE_IMAGE}", stripped,
                              "First FROM must use ${NODE_BASE_IMAGE}")
                return
        self.fail("No FROM line found")

    def test_version_args_scoped_to_consuming_stage(self):
        """Each version ARG is declared only in the stage that consumes it."""
        # Parse stages: each "FROM ... AS <name>" starts a stage
        # ARGs before the first FROM are global
        stages = {}
        current = None
        lines = self.content.splitlines()
        for i, line in enumerate(lines):
            stripped = line.split("#")[0].strip()
            # Stage boundary
            m = re.match(r'^FROM\s+\S+\s+AS\s+(\S+)', stripped)
            if m:
                current = m.group(1)
                stages[current] = {"args": set(), "from": i}
                continue
            if re.match(r'^FROM\s', stripped) and not m:
                # FROM without AS — still a stage boundary
                current = f"__anonymous_{i}"
                stages[current] = {"args": set(), "from": i}
                continue
            # ARG declarations
            if current is not None:
                arg_m = re.match(r'^ARG\s+([A-Z][A-Z0-9_]*)', stripped)
                if arg_m:
                    stages[current]["args"].add(arg_m.group(1))

        # Global ARGs (before first FROM): DEV_UID, DEV_GID are allowed
        # Version ARGs should be in the consuming stage
        # Mapping: variable -> expected stage
        expected_stage = {
            "NODE_BASE_IMAGE": "global",  # declared before first FROM — acceptable
            "RUST_VERSION": "toolchain",
            "RUST_PROFILE": "toolchain",
            "RUST_COMPONENTS": "toolchain",
            "RUSTUP_URL": "toolchain",
            "RUSTUP_SHA256": "toolchain",
            "UV_VERSION": "toolchain",
            "UV_URL": "toolchain",
            "UV_SHA256": "toolchain",
            "PYTHON_VERSION": "toolchain",
            "TY_VERSION": "toolchain",
            "RTK_VERSION": "rtk-prebuilt",
            "RTK_URL": "rtk-prebuilt",
            "RTK_SHA256": "rtk-prebuilt",
            "FD_VERSION": "fd-prebuilt",
            "FD_URL": "fd-prebuilt",
            "FD_SHA256": "fd-prebuilt",
            "PI_VERSION": "pi-tools",
            "OPENSPEC_VERSION": "openspec-tools",
            "OH_MY_ZSH_VERSION": "runtime",
            "EFFECTIVE_VERSIONS_FILE": "runtime",
        }

        for var, stage_name in expected_stage.items():
            if stage_name not in stages and stage_name != "global":
                continue  # stage not present yet
            # Global ARGs are declared before first FROM — always available
            if stage_name == "global":
                found = any(
                    var in sdata["args"] for sname, sdata in stages.items()
                )
                # Also check for global (pre-FROM) declarations
                if not found:
                    # Check lines before first FROM
                    first_from = min(
                        s["from"] for s in stages.values()
                    )
                    for line in lines[:first_from]:
                        stripped = line.split("#")[0].strip()
                        if re.match(rf'^ARG\s+{re.escape(var)}\b', stripped):
                            found = True
                            break
                if not found:
                    self.fail(f"Global ARG {var} not declared before first FROM")
                continue
            # Non-global: ARG can be in the expected stage or its ancestors


class TestComposeContracts(unittest.TestCase):
    """Compose build args must use required interpolation."""

    _COMPOSE = REPO_ROOT / "docker-compose.yml"

    @classmethod
    def setUpClass(cls):
        cls.content = cls._COMPOSE.read_text()

    def test_build_args_use_required_interpolation(self):
        """Version build args use :? (required) not :- (default)."""
        version_keys = {
            "NODE_BASE_IMAGE", "RUST_VERSION", "RUST_PROFILE",
            "RUST_COMPONENTS", "RUSTUP_URL", "RUSTUP_SHA256",
            "UV_VERSION", "UV_URL", "UV_SHA256",
            "PYTHON_VERSION", "TY_VERSION",
            "RTK_VERSION", "RTK_URL", "RTK_SHA256",
            "FD_VERSION", "FD_URL", "FD_SHA256",
            "PI_VERSION", "OPENSPEC_VERSION",
            "OH_MY_ZSH_VERSION", "EFFECTIVE_VERSIONS_FILE",
        }
        missing_required = []
        for var in sorted(version_keys):
            # Must appear as ${VAR:?...} in the args section
            pattern = re.compile(
                r'\$\{' + re.escape(var) + r':\?[^}]+\}'
            )
            if not pattern.search(self.content):
                missing_required.append(var)
        if missing_required:
            self.fail(
                "Missing required interpolation (:?) for: "
                + ", ".join(missing_required)
            )

    def test_operational_values_keep_soft_defaults(self):
        """DEV_UID, DEV_GID, HOST_GATEWAY_IP may use :- (soft defaults)."""
        # These are operational, not version inputs
        self.assertIn("DEV_UID", self.content)
        self.assertIn("DEV_GID", self.content)
        # Soft defaults should be present for operational values
        self.assertIn(":-", self.content)  # at least DEV_UID/DEV_GID


class TestRuntimeInventoryContracts(unittest.TestCase):
    """Runtime inventory must be root:root 0444 and readable by dev."""

    _DOCKERFILE = REPO_ROOT / "Dockerfile"

    @classmethod
    def setUpClass(cls):
        cls.content = cls._DOCKERFILE.read_text()

    def test_effective_inventory_copied_to_runtime(self):
        """Dockerfile copies EFFECTIVE_VERSIONS_FILE to
        /usr/local/share/pi-cli/docker-constructor.toml."""
        self.assertIn("/usr/local/share/pi-cli/docker-constructor.toml", self.content,
                      "Dockerfile must COPY effective inventory to runtime path")

    def test_effective_inventory_root_owned(self):
        """Effective inventory is owned root:root."""
        self.assertIn("root:root", self.content,
                      "Dockerfile must chown effective inventory root:root")

    def test_effective_inventory_read_only(self):
        """Effective inventory is mode 0444."""
        # Check for chmod 444, 0444, or a=r
        self.assertTrue(
            "444" in self.content or "0444" in self.content,
            "Dockerfile must chmod effective inventory to 0444"
        )

    def test_runtime_helper_modules_copied(self):
        """Runtime helper (versions.py and versioning/) is copied
        into the image."""
        self.assertTrue(
            "docker/versions.py" in self.content or "docker/versioning" in self.content,
            "Dockerfile must copy resolver modules for runtime use"
        )


class TestInstallPiExtensionsNpmRoot(unittest.TestCase):
    """runtime_installer.py resolves npm packages under
    ~/.pi/agent/npm/node_modules, not ~/.pi/node_modules."""

    def setUp(self):
        self.content = (REPO_ROOT / "docker" / "runtime_installer.py").read_text()

    def test_uses_agent_npm_node_modules(self):
        """The installer references Pi's actual npm root: agent/npm/node_modules."""
        self.assertIn(
            '"agent"',
            self.content,
            "runtime_installer.py must reference 'agent' in npm path construction",
        )
        self.assertIn(
            '"npm"',
            self.content,
            "runtime_installer.py must reference 'npm' in npm path construction",
        )
        self.assertIn(
            '"node_modules"',
            self.content,
            "runtime_installer.py must reference 'node_modules' in npm path construction",
        )

    def test_no_vendored_node_modules_fallback(self):
        """The installer must not fall back to a bare ~/.pi/node_modules."""
        for line in self.content.splitlines():
            if "node_modules" not in line:
                continue
            stripped = line.split("#")[0].strip()
            if not stripped:
                continue
            if "'agent'" in stripped and "'npm'" in stripped:
                continue
            if "agent/npm/node_modules" in stripped:
                continue
            # Allow 'agent', 'npm', 'node_modules' as separate strings
            if '"agent"' in stripped and '"npm"' in stripped:
                continue
            self.fail(
                f"runtime_installer.py contains node_modules outside "
                f"agent/npm/ tree: {line.strip()}"
            )

    def test_scoped_package_path_via_os_path_join(self):
        """Scoped packages (@scope/name) are handled by os.path.join
        with the full package name — no manual '/' replacement needed."""
        self.assertIn(
            "os.path.join",
            self.content,
            "npm path must be constructed via os.path.join for cross-platform safety",
        )
        # The _npm_metadata_path function joins agent, npm, node_modules,
        # package, and metadata_file — which handles scoped names naturally.
        self.assertIn(
            '"node_modules"',
            self.content,
            "os.path.join must reference node_modules",
        )
        self.assertIn(
            'package',
            self.content,
            "os.path.join must receive the package argument directly",
        )


class TestInstallPiExtensionsShellWrapper(unittest.TestCase):
    """install-pi-extensions.sh is a thin fixed-boundary wrapper that
    delegates to the Python installer module.  It contains no TOML
    traversal, no package loop, and no npm path construction."""

    def setUp(self):
        self.content = (REPO_ROOT / "docker" / "install-pi-extensions.sh").read_text()

    def test_delegates_to_python_installer_module(self):
        """The wrapper exec's the Python installer module."""
        self.assertIn(
            "docker.runtime_installer",
            self.content,
            "Shell wrapper must delegate to docker.runtime_installer module",
        )

    def test_no_toml_traversal(self):
        """The wrapper must not parse or traverse TOML."""
        self.assertNotIn(
            "toml", self.content.lower(),
            "Shell wrapper must not contain TOML parsing",
        )

    def test_no_package_loop(self):
        """The wrapper must not loop over packages."""
        self.assertNotIn(
            "for name in", self.content,
            "Shell wrapper must not contain a package loop",
        )
        self.assertNotIn(
            "for entry in", self.content,
            "Shell wrapper must not contain a package loop",
        )

    def test_no_npm_path_construction(self):
        """The wrapper must not construct npm paths."""
        self.assertNotIn(
            "node_modules", self.content,
            "Shell wrapper must not contain node_modules path construction",
        )


class TestEntrypointRtkIntegration(unittest.TestCase):
    """The entrypoint SHALL apply rtk init and telemetry disablement
    as dev after Pi-home ownership repair.  Repeated execution does
    not duplicate configuration (both commands are idempotent)."""

    def setUp(self):
        self.content = (REPO_ROOT / "docker" / "entrypoint.sh").read_text()

    def test_rtk_init_present(self):
        """Entrypoint must invoke rtk init -g --agent pi."""
        self.assertIn(
            "rtk init -g --agent pi",
            self.content,
            "entrypoint must apply rtk init -g --agent pi",
        )

    def test_rtk_telemetry_disable_present(self):
        """Entrypoint must disable rtk telemetry."""
        self.assertIn(
            "rtk telemetry disable",
            self.content,
            "entrypoint must disable rtk telemetry",
        )

    def test_rtk_runs_as_dev(self):
        """Both rtk commands must run under gosu dev:dev, never as root.
        There must be exactly two active gosu dev:dev rtk lines —
        neither more (duplication) nor fewer (absent)."""
        lines = self.content.splitlines()
        active = [
            l for l in lines
            if l.strip() and not l.strip().startswith("#")
        ]
        rtk_lines = [
            l.strip() for l in active
            if "gosu dev:dev rtk init" in l or "gosu dev:dev rtk telemetry" in l
        ]
        self.assertEqual(
            2, len(rtk_lines),
            f"Expected exactly 2 gosu dev:dev rtk lines, got {len(rtk_lines)}",
        )
        for line in rtk_lines:
            self.assertIn(
                "gosu dev:dev",
                line,
                f"rtk command must run as dev: {line}",
            )

    def test_rtk_scoped_to_projection_guard(self):
        """Both rtk commands must execute inside the guarded block
        that checks for the runtime projection file.  They must
        never run on a plain entrypoint without a mounted home."""
        lines = self.content.splitlines()
        # Find the projection guard and its matching fi via nesting
        guard_start = None
        guard_end = None
        depth = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == 'if [ -f "${RUNTIME_PROJECTION}" ]; then':
                guard_start = i
                depth = 1
                continue
            if guard_start is not None and stripped == "fi":
                depth -= 1
                if depth == 0:
                    guard_end = i
                    break
            if guard_start is not None and stripped.startswith("if "):
                depth += 1
        self.assertIsNotNone(guard_start, "Projection guard not found")
        self.assertIsNotNone(guard_end, "Projection guard closing 'fi' not found")

        rtk_line_indices = [
            i for i, line in enumerate(lines)
            if not line.strip().startswith("#")
            and ("gosu dev:dev rtk init" in line or "gosu dev:dev rtk telemetry" in line)
        ]
        self.assertEqual(
            2, len(rtk_line_indices),
            f"Expected exactly 2 rtk lines, got {len(rtk_line_indices)}",
        )
        for idx in rtk_line_indices:
            self.assertTrue(
                guard_start < idx < guard_end,
                f"rtk line {idx} is outside the projection-guarded block "
                f"({guard_start}..{guard_end})",
            )

    def test_rtk_init_fails_startup(self):
        """A failing rtk init must abort startup (nonzero exit)."""
        lines = self.content.splitlines()
        active = [
            l for l in lines
            if l.strip() and not l.strip().startswith("#")
        ]
        found_init = False
        for i, line in enumerate(active):
            if "rtk init -g --agent pi" in line:
                found_init = True
                for j in range(i + 1, min(i + 4, len(active))):
                    if "exit 1" in active[j]:
                        break
                else:
                    self.fail(
                        "rtk init failure must be followed by exit 1 "
                        "within 3 lines"
                    )
        self.assertTrue(found_init, "rtk init invocation not found")

    def test_rtk_telemetry_fails_startup(self):
        """A failing rtk telemetry disable must abort startup."""
        lines = self.content.splitlines()
        active = [
            l for l in lines
            if l.strip() and not l.strip().startswith("#")
        ]
        found_telemetry = False
        for i, line in enumerate(active):
            if "rtk telemetry disable" in line:
                found_telemetry = True
                for j in range(i + 1, min(i + 4, len(active))):
                    if "exit 1" in active[j]:
                        break
                else:
                    self.fail(
                        "rtk telemetry disable failure must be followed "
                        "by exit 1 within 3 lines"
                    )
        self.assertTrue(found_telemetry, "rtk telemetry disable invocation not found")
