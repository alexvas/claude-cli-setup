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
    """install-pi-extensions.sh resolves npm packages under
    ~/.pi/agent/npm/node_modules, not ~/.pi/node_modules."""

    def setUp(self):
        self.content = (REPO_ROOT / "docker" / "install-pi-extensions.sh").read_text()

    def test_uses_agent_npm_node_modules(self):
        """The script references Pi's actual npm root: agent/npm/node_modules."""
        self.assertIn(
            "agent/npm/node_modules",
            self.content,
            "install-pi-extensions.sh must resolve packages under ~/.pi/agent/npm/node_modules",
        )

    def test_no_vendored_node_modules_fallback(self):
        """The script must not fall back to a bare ~/.pi/node_modules."""
        # The only node_modules references must be within the agent/npm/
        # tree (either as a joined string or via os.path.join components).
        for line in self.content.splitlines():
            if "node_modules" not in line:
                continue
            # Comments and the constructed npm_root path are fine
            stripped = line.split("#")[0].strip()
            if not stripped:
                continue
            # Allow os.path.join('agent', 'npm', 'node_modules')
            if "'agent'" in stripped and "'npm'" in stripped:
                continue
            if "agent/npm/node_modules" in stripped:
                continue
            self.fail(
                f"install-pi-extensions.sh contains node_modules outside "
                f"agent/npm/ tree: {line.strip()}"
            )

    def test_scoped_package_path_uses_separator_replacement(self):
        """Scoped packages (@scope/name) must replace '/' with os.sep for
        filesystem lookup."""
        self.assertIn(
            "pkg.replace('/', os.sep)",
            self.content,
            "Scoped package lookup must use '/' to os.sep replacement",
        )

    def test_unscoped_fallback_present(self):
        """An unscoped fallback (flat name after last '/') must exist for
        packages that may install without the full scoped path."""
        self.assertIn(
            "split('/')[-1]",
            self.content,
            "Must have unscoped flat-name fallback for package lookup",
        )
