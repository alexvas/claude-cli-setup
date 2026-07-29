"""RED — Project Launcher Tests (Stage 11.1).

Failing tests for project selection, pi-N allocation, and
launch-vector assembly.  All tests use injected fakes — no Docker
daemon, subprocess, filesystem, or network access.

Design constraints:
  - ``--main-project PATH`` selects the main project explicitly.
  - ``--project PATH`` (repeatable) adds optional projects.
  - ``--tui`` invokes interactive project selection.
  - Project-selection precedence:
    1. Explicit ``--main-project``
    2. TUI selection (when ``--tui`` is requested)
    3. Automatic selection (if retained)
    4. Otherwise: actionable ``NoMainProjectError``
  - The first ``--project`` is never silently promoted to main.
  - pi-N allocation uses ``docker ps -a`` inspection, best-effort.
  - The launch vector assembles into :class:`RunRenderInputs` and
    delegates to :func:`render_run_vector`.
"""

from __future__ import annotations

import unittest

from docker.launcher import (
    ContainerInspectError,
    ContainerNameInspector,
    NoMainProjectError,
    ProjectSelection,
    ProjectSelector,
)
from docker.versioning.rendering import RunRenderInputs, render_run_vector


# ═══════════════════════════════════════════════════════════════════
# 11.1.1 - Project selection from CLI flags
# ═══════════════════════════════════════════════════════════════════


class TestProjectSelectionFromArgs(unittest.TestCase):
    """Project selection contract: the CLI parser MUST support the
    full flag surface described in the Phase 11 plan, and project
    resolution MUST produce a :class:`ProjectSelection` that
    observes the documented precedence rules."""

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _select(*, selector: ProjectSelector | None = None, **flags) -> ProjectSelection:
        """Simulate resolving project selection from parsed CLI flags.

        Mapped to the future ``resolve_project_selection()`` in
        ``docker/launcher.py``.
        """
        from docker.launcher import resolve_project_selection
        return resolve_project_selection(
            main_project=flags.get("main_project"),
            projects=flags.get("projects", ()),
            tui=flags.get("tui", False),
            base_project_dir=flags.get("base_project_dir"),
            selector=selector,
        )

    # ── explicit main project ────────────────────────────────────

    def test_explicit_main_project_no_optional(self) -> None:
        sel = self._select(main_project="/work/p1")
        self.assertEqual(sel.main_project, "/work/p1")
        self.assertEqual(sel.optional_projects, ())

    def test_explicit_main_project_with_one_optional(self) -> None:
        sel = self._select(
            main_project="/work/p1", projects=["/work/p2"],
        )
        self.assertEqual(sel.main_project, "/work/p1")
        self.assertEqual(sel.optional_projects, ("/work/p2",))

    def test_explicit_main_project_with_two_optional(self) -> None:
        sel = self._select(
            main_project="/work/p1",
            projects=["/work/p2", "/work/p3"],
        )
        self.assertEqual(sel.main_project, "/work/p1")
        self.assertEqual(sel.optional_projects, ("/work/p2", "/work/p3"))

    def test_explicit_main_project_with_many_optional(self) -> None:
        sel = self._select(
            main_project="/work/main",
            projects=[f"/work/p{i}" for i in range(5)],
        )
        self.assertEqual(sel.main_project, "/work/main")
        self.assertEqual(len(sel.optional_projects), 5)

    # ── no main project → error ──────────────────────────────────

    def test_no_main_project_raises(self) -> None:
        with self.assertRaises(NoMainProjectError):
            self._select()

    def test_no_main_project_only_optional_raises(self) -> None:
        """The first --project is never silently treated as main."""
        with self.assertRaises(NoMainProjectError):
            self._select(projects=["/work/p1"])

    def test_no_main_project_multiple_optional_raises(self) -> None:
        with self.assertRaises(NoMainProjectError):
            self._select(projects=["/work/p1", "/work/p2"])

    # ── stable optional ordering ─────────────────────────────────

    def test_optional_projects_preserve_insertion_order(self) -> None:
        sel = self._select(
            main_project="/work/main",
            projects=["/work/z", "/work/a", "/work/m"],
        )
        self.assertEqual(
            sel.optional_projects,
            ("/work/z", "/work/a", "/work/m"),
        )

    # ── duplicate rejection ──────────────────────────────────────

    def test_main_equals_optional_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/p1", projects=["/work/p1"],
            )

    def test_duplicate_optional_paths_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/p1",
                projects=["/work/p2", "/work/p2"],
            )

    # ── path validation ──────────────────────────────────────────

    def test_relative_main_project_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(main_project="relative/path")

    def test_relative_optional_project_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/p1",
                projects=["relative/path"],
            )

    def test_empty_main_project_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(main_project="")

    def test_empty_optional_project_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/p1", projects=[""],
            )

    # ── normalized-path duplicate detection ──────────────────────

    def test_normalized_duplicate_main_and_optional_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/a",
                projects=["/work/./a"],
            )

    def test_normalized_duplicate_optionals_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/main",
                projects=["/work/a", "/work/./a"],
            )

    def test_normalized_duplicate_deep_traversal_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._select(
                main_project="/work/main",
                projects=["/work/a/b/../c", "/work/a/c"],
            )

    # ── TUI selection (injected ProjectSelector boundary) ────────

    def test_tui_selects_main_project(self) -> None:
        """When --tui is requested and the selector returns a
        ProjectSelection, that selection becomes the result."""
        sel = self._select(
            tui=True,
            selector=_FakeSelector("/work/tui-main"),
        )
        self.assertEqual(sel.main_project, "/work/tui-main")
        self.assertEqual(sel.optional_projects, ())

    def test_tui_selects_main_plus_optional_projects(self) -> None:
        """The TUI can return optional projects alongside the
        main project — they are preserved in the result."""
        sel = self._select(
            tui=True,
            selector=_FakeSelector(
                "/work/tui-main", ("/work/tui-opt1", "/work/tui-opt2"),
            ),
        )
        self.assertEqual(sel.main_project, "/work/tui-main")
        self.assertEqual(
            sel.optional_projects,
            ("/work/tui-opt1", "/work/tui-opt2"),
        )

    def test_tui_cancellation_returns_error(self) -> None:
        """When --tui is requested but the selector returns None
        (user cancelled), the result is NoMainProjectError."""
        with self.assertRaises(NoMainProjectError):
            self._select(tui=True, selector=_FakeSelector.cancelled())

    def test_tui_without_main_flag_still_requires_selection(self) -> None:
        """--tui alone with no --main-project must still resolve a
        main project through the TUI; cancellation is an error."""
        with self.assertRaises(NoMainProjectError):
            self._select(
                tui=True, projects=["/work/p1"],
                selector=_FakeSelector.cancelled(),
            )

    # ── TUI + explicit main still works ──────────────────────────

    def test_tui_with_explicit_main_project(self) -> None:
        """Explicit --main-project takes precedence over --tui.
        The selector is not consulted."""
        sel = self._select(
            main_project="/work/main", tui=True,
            selector=_FakeSelector("/work/should-not-be-used"),
        )
        self.assertEqual(sel.main_project, "/work/main")

    def test_explicit_main_ignores_tui_cancellation(self) -> None:
        """When --main-project is given, even a cancelled TUI must
        not prevent the selection — explicit beats TUI."""
        sel = self._select(
            main_project="/work/main", tui=True,
            selector=_FakeSelector.cancelled(),
        )
        self.assertEqual(sel.main_project, "/work/main")

    # ── malformed TUI results ───────────────────────────────────

    def test_tui_result_main_equals_optional_rejected(self) -> None:
        """The resolver validates the selector's result — a
        returned main_project that duplicates an optional must
        be rejected, not blindly trusted."""
        with self.assertRaises(ValueError):
            self._select(
                tui=True,
                selector=_FakeSelector.from_raw("/work/p1", ("/work/p1",)),
            )

    def test_tui_result_duplicate_optional_paths_rejected(self) -> None:
        """The resolver must reject a selector result where two
        optional projects are the same path."""
        with self.assertRaises(ValueError):
            self._select(
                tui=True,
                selector=_FakeSelector.from_raw(
                    "/work/main", ("/work/opt", "/work/opt"),
                ),
            )

    def test_tui_result_normalized_duplicate_rejected(self) -> None:
        """The resolver must detect duplicates after normalization,
        e.g. /work/a and /work/./a."""
        with self.assertRaises(ValueError):
            self._select(
                tui=True,
                selector=_FakeSelector.from_raw(
                    "/work/main", ("/work/a", "/work/./a"),
                ),
            )

    def test_tui_result_relative_main_project_rejected(self) -> None:
        """A selector that returns a relative main_project path
        must be rejected — absolute paths are required."""
        with self.assertRaises(ValueError):
            self._select(
                tui=True,
                selector=_FakeSelector.from_raw(
                    "relative/path", (),
                ),
            )

    def test_tui_result_empty_main_project_rejected(self) -> None:
        """A selector that returns an empty main_project must be
        rejected."""
        with self.assertRaises(ValueError):
            self._select(
                tui=True,
                selector=_FakeSelector.from_raw("", ()),
            )


# ═══════════════════════════════════════════════════════════════════
# 11.1.3 - pi-N allocation
# ═══════════════════════════════════════════════════════════════════


class _FakeSelector:
    """Fake :class:`ProjectSelector` for deterministic tests."""

    def __init__(
        self,
        main: str,
        optionals: tuple[str, ...] = (),
    ) -> None:
        self._main = main
        self._optionals = optionals

    @classmethod
    def cancelled(cls) -> "_FakeSelector":
        """Return a selector that simulates user cancellation."""
        inst = cls.__new__(cls)
        inst._main = ""  # signals cancelled
        inst._optionals = ()
        return inst

    @classmethod
    def from_raw(
        cls, main: str, optionals: tuple[str, ...],
    ) -> "_FakeSelector":
        """Return a selector that returns a pre-built
        :class:`ProjectSelection` with potentially invalid fields.

        Uses ``object.__setattr__`` to bypass ``__post_init__``
        validation so the resolver's own validation can be tested.
        """
        sel = ProjectSelection.__new__(ProjectSelection)
        object.__setattr__(sel, "main_project", main)
        object.__setattr__(sel, "optional_projects", optionals)
        inst = cls.__new__(cls)
        inst._result = sel
        return inst

    def select(self) -> ProjectSelection | None:
        if hasattr(self, "_result"):
            return self._result  # from_raw
        if not self._main:
            return None
        return ProjectSelection(
            main_project=self._main,
            optional_projects=self._optionals,
        )


class FakeContainerNameInspector:
    """Fake :class:`ContainerNameInspector` for deterministic tests."""

    def __init__(self, names: set[str] | None = None,
                 *, fail_with: Exception | None = None) -> None:
        self._names = names or set()
        self._fail_with = fail_with

    def list_names(self) -> set[str]:
        if self._fail_with is not None:
            raise self._fail_with
        return self._names


class TestPiNAllocation(unittest.TestCase):
    """pi-N allocation against an injected Docker-inspection boundary.

    Uses ``docker ps -a --format '{{.Names}}'`` to discover existing
    container names, then selects the lowest free ``pi-N`` number.
    Allocation is best-effort: another process may claim the name
    before ``docker run`` executes.
    """

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _allocate(
        inspector: ContainerNameInspector,
    ) -> str:
        from docker.launcher import allocate_pi_name
        return allocate_pi_name(inspector)

    # ── fresh namespace ──────────────────────────────────────────

    def test_no_existing_names_returns_pi_1(self) -> None:
        inspector = FakeContainerNameInspector(set())
        self.assertEqual(self._allocate(inspector), "pi-1")

    def test_no_matching_names_returns_pi_1(self) -> None:
        inspector = FakeContainerNameInspector({"nginx", "redis"})
        self.assertEqual(self._allocate(inspector), "pi-1")

    # ── pi-1 taken ───────────────────────────────────────────────

    def test_pi_1_exists_returns_pi_2(self) -> None:
        inspector = FakeContainerNameInspector({"pi-1"})
        self.assertEqual(self._allocate(inspector), "pi-2")

    def test_pi_1_and_pi_2_exist_returns_pi_3(self) -> None:
        inspector = FakeContainerNameInspector({"pi-1", "pi-2"})
        self.assertEqual(self._allocate(inspector), "pi-3")

    # ── sparse allocation ────────────────────────────────────────

    def test_pi_1_and_pi_3_exist_returns_pi_2(self) -> None:
        """Lowest free number is pi-2 even though pi-3 exists."""
        inspector = FakeContainerNameInspector({"pi-1", "pi-3"})
        self.assertEqual(self._allocate(inspector), "pi-2")

    def test_unordered_names_still_produce_lowest_free(self) -> None:
        inspector = FakeContainerNameInspector({"pi-5", "pi-2", "pi-1"})
        self.assertEqual(self._allocate(inspector), "pi-3")

    def test_many_existing_pi_names(self) -> None:
        inspector = FakeContainerNameInspector(
            {f"pi-{i}" for i in range(1, 50)}
        )
        self.assertEqual(self._allocate(inspector), "pi-50")

    # ── non-pi names do not reserve slots ────────────────────────

    def test_pi_1_old_does_not_reserve_pi_1(self) -> None:
        inspector = FakeContainerNameInspector({"pi-1-old"})
        self.assertEqual(self._allocate(inspector), "pi-1")

    def test_xpi_1_does_not_reserve_pi_1(self) -> None:
        inspector = FakeContainerNameInspector({"xpi-1"})
        self.assertEqual(self._allocate(inspector), "pi-1")

    def test_pi_a_does_not_reserve_any_number(self) -> None:
        inspector = FakeContainerNameInspector({"pi-a", "pi-b"})
        self.assertEqual(self._allocate(inspector), "pi-1")

    def test_pi_without_number_ignored(self) -> None:
        inspector = FakeContainerNameInspector({"pi-"})
        self.assertEqual(self._allocate(inspector), "pi-1")

    def test_pi_with_leading_zero_parsed(self) -> None:
        """pi-01 reserves pi-1 because pi-01 is an integer 1."""
        inspector = FakeContainerNameInspector({"pi-01"})
        self.assertEqual(self._allocate(inspector), "pi-2")

    def test_pi_with_large_number(self) -> None:
        inspector = FakeContainerNameInspector({"pi-999999999999"})
        result = self._allocate(inspector)
        self.assertEqual(result, "pi-1")

    # ── inspection failures ──────────────────────────────────────

    def test_inspection_failure_is_actionable(self) -> None:
        inspector = FakeContainerNameInspector(
            fail_with=ContainerInspectError("docker not found"),
        )
        with self.assertRaises(ContainerInspectError) as ctx:
            self._allocate(inspector)
        self.assertIn("docker not found", str(ctx.exception))

    def test_docker_not_installed_structured(self) -> None:
        inspector = FakeContainerNameInspector(
            fail_with=ContainerInspectError(
                "Docker executable not found",
            ),
        )
        with self.assertRaises(ContainerInspectError) as ctx:
            self._allocate(inspector)
        self.assertIn("Docker executable", str(ctx.exception))

    # ── malformed output ─────────────────────────────────────────

    def test_malformed_number_skipped(self) -> None:
        """A malformed pi name like 'pi-abc' must not crash the
        allocator — it is simply ignored."""
        inspector = FakeContainerNameInspector({"pi-1", "pi-abc"})
        self.assertEqual(self._allocate(inspector), "pi-2")

    def test_all_malformed_falls_back_to_pi_1(self) -> None:
        inspector = FakeContainerNameInspector({"pi-abc", "pi-xyz"})
        self.assertEqual(self._allocate(inspector), "pi-1")


# ═══════════════════════════════════════════════════════════════════
# 11.1.4 - Launch-vector contract
# ═══════════════════════════════════════════════════════════════════


class TestLaunchVectorContract(unittest.TestCase):
    """Integration of project selection → :class:`RunRenderInputs` →
    :func:`render_run_vector`.  The launcher must produce a correct
    ``docker run`` vector from selected projects without Compose."""

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_inputs(
        selection: ProjectSelection,
        *,
        image: str = "pi-cli-pi:latest",
        container_name: str = "pi-1",
        pi_home_host: str = "/home/alice/.pi",
        projection_host_path: str = (
            "/home/dev/.pi-cli/.docker-generated/runtime/proj.toml"
        ),
        projection_container_path: str = (
            "/run/pi-cli/docker-constructor.runtime.toml"
        ),
        gateway: str = "host-gateway",
        tty: bool = True,
        stdin_open: bool = True,
        chown_on_start: str | None = None,
    ) -> RunRenderInputs:
        from docker.launcher import build_run_inputs
        return build_run_inputs(
            selection=selection,
            image=image,
            container_name=container_name,
            pi_home_host=pi_home_host,
            projection_host_path=projection_host_path,
            projection_container_path=projection_container_path,
            gateway=gateway,
            tty=tty,
            stdin_open=stdin_open,
            chown_on_start=chown_on_start,
        )

    @staticmethod
    def _vector(inputs: RunRenderInputs) -> tuple[str, ...]:
        return render_run_vector(inputs)

    # ── basic shape ──────────────────────────────────────────────

    def test_command_starts_with_docker_run_rm(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        args = self._vector(self._build_inputs(sel))
        self.assertEqual(args[:3], ("docker", "run", "--rm"))

    def test_no_compose_in_output(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        args = self._vector(self._build_inputs(sel))
        self.assertNotIn("compose", args)
        self.assertNotIn("-f", args)
        self.assertNotIn("--file", args)

    # ── container name ───────────────────────────────────────────

    def test_container_name_in_vector(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, container_name="pi-7")
        args = self._vector(inputs)
        name_idx = args.index("--name")
        self.assertEqual(args[name_idx + 1], "pi-7")

    # ── Pi home mount ────────────────────────────────────────────

    def test_pi_home_mounted_to_container(self) -> None:
        """Host Pi home is mounted at /home/dev/.pi in the container."""
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, pi_home_host="/host/pi")
        args = self._vector(inputs)
        spec = _parse_mount_spec(args, dst="/home/dev/.pi")
        self.assertEqual(spec["src"], "/host/pi")
        self.assertEqual(spec["dst"], "/home/dev/.pi")

    # ── main project 1:1 mount + workdir ─────────────────────────

    def test_main_project_1to1_mount(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        args = self._vector(self._build_inputs(sel))
        spec = _parse_mount_spec(args, dst="/work/p1")
        self.assertEqual(spec["src"], "/work/p1")

    def test_main_project_is_workdir(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        args = self._vector(self._build_inputs(sel))
        wd_idx = args.index("--workdir")
        self.assertEqual(args[wd_idx + 1], "/work/p1")

    # ── optional projects ────────────────────────────────────────

    def test_one_optional_project_mount(self) -> None:
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=("/work/opt",),
        )
        args = self._vector(self._build_inputs(sel))
        spec = _parse_mount_spec(args, dst="/work/opt")
        self.assertEqual(spec["src"], "/work/opt")

    def test_two_optional_projects_mount(self) -> None:
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=("/work/a", "/work/b"),
        )
        args = self._vector(self._build_inputs(sel))
        spec_a = _parse_mount_spec(args, dst="/work/a")
        spec_b = _parse_mount_spec(args, dst="/work/b")
        self.assertEqual(spec_a["src"], "/work/a")
        self.assertEqual(spec_b["src"], "/work/b")

    def test_optional_projects_preserved_in_order(self) -> None:
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=("/work/z", "/work/a"),
        )
        args = self._vector(self._build_inputs(sel))
        z_idx = _find_mount(args, dst="/work/z")
        a_idx = _find_mount(args, dst="/work/a")
        self.assertLess(z_idx, a_idx, "optional mounts must preserve order")

    # ── PROJECT_PATH_* environment ───────────────────────────────

    def test_project_path_1_is_main(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        args = self._vector(self._build_inputs(sel))
        self.assertIn("PROJECT_PATH_1=/work/p1", args)

    def test_project_path_2_is_first_optional(self) -> None:
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=("/work/opt1", "/work/opt2"),
        )
        args = self._vector(self._build_inputs(sel))
        self.assertIn("PROJECT_PATH_1=/work/main", args)
        self.assertIn("PROJECT_PATH_2=/work/opt1", args)
        self.assertIn("PROJECT_PATH_3=/work/opt2", args)

    def test_project_path_count_matches_projects(self) -> None:
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=("/work/a", "/work/b", "/work/c"),
        )
        args = self._vector(self._build_inputs(sel))
        project_path_count = sum(
            1 for a in args if a.startswith("PROJECT_PATH_")
        )
        self.assertEqual(project_path_count, 4)  # 1 main + 3 optional

    def test_many_optionals_each_mounted_and_exported(self) -> None:
        """Every optional project appears as a 1:1 mount *and* as a
        consecutive PROJECT_PATH_N with no gaps in numbering."""
        optionals = tuple(f"/work/opt{i}" for i in range(1, 6))
        sel = ProjectSelection(
            main_project="/work/main",
            optional_projects=optionals,
        )
        args = self._vector(self._build_inputs(sel))

        # Main project: mount + PROJECT_PATH_1
        main_spec = _parse_mount_spec(args, dst="/work/main")
        self.assertEqual(main_spec["src"], "/work/main")
        self.assertIn("PROJECT_PATH_1=/work/main", args)

        # Each optional: mounted 1:1 and exported consecutively
        for i, path in enumerate(optionals, start=2):
            spec = _parse_mount_spec(args, dst=path)
            self.assertEqual(
                spec["src"], path,
                f"optional project {path!r} must be mounted 1:1",
            )
            self.assertIn(
                f"PROJECT_PATH_{i}={path}", args,
                f"{path!r} must be exported as PROJECT_PATH_{i}",
            )

        # No gaps: exactly N+1 PROJECT_PATH_ vars for N optionals
        exported = sorted(
            a for a in args if a.startswith("PROJECT_PATH_")
        )
        expected = [
            f"PROJECT_PATH_{i}={p}"
            for i, p in enumerate(
                ("/work/main",) + optionals, start=1,
            )
        ]
        self.assertEqual(
            exported, expected,
            "PROJECT_PATH_* must be consecutive with no gaps",
        )

    # ── gateway ──────────────────────────────────────────────────

    def test_gateway_in_add_host(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, gateway="192.168.1.1")
        args = self._vector(inputs)
        self.assertIn("--add-host", args)
        host_idx = args.index("--add-host")
        self.assertEqual(
            args[host_idx + 1], "host.docker.internal:192.168.1.1",
        )

    # ── image and command ────────────────────────────────────────

    def test_image_placed_correctly(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, image="my-image:tag")
        args = self._vector(inputs)
        # Image must be the last argument before any passthrough command.
        self.assertIn("my-image:tag", args)

    # ── chown_on_start ───────────────────────────────────────────

    def test_chown_on_start_set(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, chown_on_start="1")
        args = self._vector(inputs)
        self.assertIn("CHOWN_WORK_ON_START=1", args)

    def test_no_chown_on_start_when_none(self) -> None:
        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, chown_on_start=None)
        args = self._vector(inputs)
        chown_vars = [a for a in args if "CHOWN_WORK_ON_START" in a]
        self.assertEqual(chown_vars, [])

    # ── full pi-N integration ────────────────────────────────────

    def test_pi_n_allocation_integrated_into_vector(self) -> None:
        """End-to-end: allocate pi-N from an inspector, produce a
        vector where --name matches the allocated name."""
        inspector = FakeContainerNameInspector({"pi-1", "pi-2"})
        from docker.launcher import allocate_pi_name

        name = allocate_pi_name(inspector)
        self.assertEqual(name, "pi-3")

        sel = ProjectSelection(main_project="/work/p1")
        inputs = self._build_inputs(sel, container_name=name)
        args = self._vector(inputs)

        name_idx = args.index("--name")
        self.assertEqual(args[name_idx + 1], "pi-3")


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════


def _find_mount(args: tuple[str, ...], *, dst: str) -> int:
    """Find the start index of a ``--mount`` argument by
    destination path.  Returns the index of ``--mount``."""
    for i, a in enumerate(args):
        if a == "--mount":
            spec = args[i + 1]
            for part in spec.split(","):
                if part == f"dst={dst}":
                    return i
    raise ValueError(f"mount with dst={dst!r} not found in args")


def _parse_mount_spec(
    args: tuple[str, ...], *, dst: str,
) -> dict[str, str]:
    """Find a ``--mount`` by *dst* and return its spec as a
    ``{key: value}`` dict."""
    idx = _find_mount(args, dst=dst)
    spec_str = args[idx + 1]
    result: dict[str, str] = {}
    for part in spec_str.split(","):
        k, _, v = part.partition("=")
        result[k] = v
    return result


if __name__ == "__main__":
    unittest.main()
