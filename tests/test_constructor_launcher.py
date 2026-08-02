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

import os
import unittest

from docker.launcher import (
    ContainerInspectError,
    ContainerNameInspector,
    DockerContainerInspector,
    DockerRunExecutor,
    NoMainProjectError,
    ProcessResult,
    ProcessRunner,
    ProjectSelection,
    ProjectSelector,
    ProjectionFactory,
    RunExecutor,
    RunRequest,
    RunResult,
)
from docker.versioning.rendering import RunRenderInputs, render_run_vector
from docker.versioning.dispatch_types import ExitKind


# ═══════════════════════════════════════════════════════════════════
# Shared test doubles
# ═══════════════════════════════════════════════════════════════════


class FakeProcessRunner(ProcessRunner):
    """Deterministic :class:`ProcessRunner` that consumes canned
    :class:`ProcessResult` responses in FIFO order.  Falls back to
    a non-zero result when no responses remain."""

    def __init__(self, responses: list[ProcessResult] | None = None) -> None:
        self._responses: list[ProcessResult] = list(responses or [])
        self.calls: list[list[str]] = []

    def run(self, argv: list[str]) -> ProcessResult:
        self.calls.append(argv)
        if self._responses:
            return self._responses.pop(0)
        return ProcessResult(
            argv=tuple(argv),
            return_code=1,
            stdout="",
            stderr=f"no canned response for {argv[0]}",
        )

    def add(self, result: ProcessResult) -> None:
        self._responses.append(result)


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


# ═══════════════════════════════════════════════════════════════════
# 11.2 - Run transaction (orchestrate_run)
# ═══════════════════════════════════════════════════════════════════


class FakeRunExecutor:
    """Recording :class:`RunExecutor` for deterministic tests."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        fail_with: Exception | None = None,
    ) -> None:
        self.returncode = returncode
        self._fail_with = fail_with
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        if self._fail_with is not None:
            raise self._fail_with
        self.calls.append(argv)
        return ProcessResult(
            argv=argv,
            return_code=self.returncode,
            stdout="ok" if self.returncode == 0 else "",
            stderr="" if self.returncode == 0 else "container failed",
        )


class _BombExecutor:
    """Executor that explodes if ``run()`` is ever invoked.

    Used in dry-run tests to prove the orchestrator never calls
    Docker — including ``docker run``.  Any invocation is a test
    failure."""

    def run(self, argv: tuple[str, ...]) -> ProcessResult:
        raise AssertionError(
            "_BombExecutor.run() called — dry-run must not invoke Docker",
        )


class _BombInspector:
    """Inspector that explodes if ``list_names()``
    is ever invoked.

    Used in dry-run tests to prove the orchestrator never calls
    ``docker ps`` for pi-N allocation.  Any invocation is a test
    failure."""

    def list_names(self) -> frozenset[str]:
        raise AssertionError(
            "_BombInspector.list_names() called — "
            "dry-run must not invoke docker ps",
        )


class _BombProjectionFactory:
    """Projection factory that explodes if called.

    Used in dry-run tests to prove the orchestrator never creates
    a temporary projection file — not even "create then delete".
    """

    def __call__(
        self,
        projection: object,
        *,
        parent_dir: str,
    ) -> object:
        raise AssertionError(
            "_BombProjectionFactory called — "
            "dry-run must not create projection files",
        )


class _RecordingHandle:
    """Spy context manager that records enter/exit calls and
    creates/removes a real file for observable cleanup assertions."""

    def __init__(self, path: str, content_hash: str) -> None:
        self._path = path
        self._hash = content_hash
        self.entered = False
        self.exited = False
        self.exit_args: tuple[object, object, object] | None = None

    @property
    def path(self) -> str:
        return self._path

    @property
    def content_hash(self) -> str:
        return self._hash

    def __enter__(self) -> "_RecordingHandle":
        self.entered = True
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as fh:
            fh.write("fake-projection-content")
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> bool:
        self.exited = True
        self.exit_args = (exc_type, exc_val, exc_tb)
        if os.path.exists(self._path):
            os.remove(self._path)
        return False  # never suppress


class RecordingProjectionFactory:
    """Spy :class:`ProjectionFactory` that records every call and
    returns :class:`_RecordingHandle` instances for inspection.

    The content hash is computed from the serialized projection so
    override-selection tests can prove artifact switching."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []
        self.handles: list[_RecordingHandle] = []

    def __call__(
        self,
        projection: object,
        *,
        parent_dir: str,
    ) -> _RecordingHandle:
        import dataclasses
        import hashlib
        import json

        # Convert the projection to a plain dict for hashing.
        # dataclasses.asdict chokes on MappingProxyType, so we
        # rebuild the extensions dict manually.
        raw_proj: dict[str, object] = {
            "extensions": {
                name: dataclasses.asdict(entry)
                for name, entry in getattr(
                    projection, "extensions", {}
                ).items()
            }
        }
        raw = json.dumps(raw_proj, sort_keys=True, default=str)
        content_hash = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()
        path = os.path.join(parent_dir, "proj.toml")
        h = _RecordingHandle(path, content_hash)
        self.calls.append((projection, parent_dir))
        self.handles.append(h)
        return h


class TestRunTransaction(unittest.TestCase):
    """Run-transaction contract for :func:`orchestrate_run`.

    Covers: runtime overrides, private projection creation, read-only
    mount, gateway mapping, TTY modes, dry-run, Docker failure, and
    projection cleanup."""

    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        # projection_parent_dir must contain the .docker-generated/runtime
        # segments required by run-renderer validation.
        self._proj_parent = os.path.join(
            self._tmpdir.name, ".docker-generated", "runtime",
        )
        # Build a fixture TOML that adds a second artifact version for
        # pi-read so override-selection tests can prove a non-default
        # artifact is resolved.
        self._inventory_path = self._make_fixture_toml()

    def _make_fixture_toml(self) -> str:
        """Copy the real docker-constructor.toml and inject an
        additional ``pi-read`` artifact at version ``0.3.0`` so
        override-version selection is observable."""
        import shutil
        real = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "docker-constructor.toml"),
        )
        fixture = os.path.join(self._tmpdir.name, "docker-constructor.toml")
        shutil.copy2(real, fixture)
        with open(fixture, "a") as fh:
            fh.write(
                '\n'
                '[runtime.pi-extensions.pi-read.artifacts."0.3.0"]\n'
                'url = "https://registry.npmjs.org/@arcanemachine/pi-read/-/pi-read-0.3.0.tgz"\n'
                'integrity = "sha512-HVRCJdfUNS4642pHcL57fyprYKNZGK2Szx+7i2DHTIAacwqTdlxGN7NwiVi2QtXSwcC1j7/w8xZeNJ9u6ioQ6g=="\n'
            )
        return fixture

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    # ── helpers ──────────────────────────────────────────────────

    def _request(self, **overrides: object) -> RunRequest:
        from docker.launcher import orchestrate_run  # keep import alive
        kwargs: dict[str, object] = {
            "inventory_path": self._inventory_path,
            "image": "pi-cli-pi:latest",
            "selection": ProjectSelection(main_project="/work/p1"),
            "pi_home_host": "/home/alice/.pi",
            "projection_parent_dir": self._proj_parent,
            "_create_projection": RecordingProjectionFactory(),
        }
        kwargs.update(overrides)
        return RunRequest(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _run(req: RunRequest) -> RunResult:
        from docker.launcher import orchestrate_run
        return orchestrate_run(req)

    # ── happy path ───────────────────────────────────────────────

    def test_successful_run_produces_run_args(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        self.assertTrue(len(result.run_args) > 0,
                        "run_args must be non-empty")
        self.assertEqual(result.run_args[:3], ("docker", "run", "--rm"))

    def test_successful_run_invokes_executor(self) -> None:
        executor = FakeRunExecutor(returncode=0)
        req = self._request(
            executor=executor,
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        self.assertEqual(len(executor.calls), 1,
                         "executor must be called exactly once")
        self.assertEqual(
            executor.calls[0], result.run_args,
            "executor must receive exactly the rendered args",
        )

    def test_process_result_captured(self) -> None:
        executor = FakeRunExecutor(returncode=0)
        req = self._request(
            executor=executor,
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIsNotNone(result.process_result)
        self.assertEqual(result.process_result.return_code, 0)  # type: ignore[union-attr]

    # ── private projection ───────────────────────────────────────

    def test_projection_created_under_docker_generated_runtime(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIsNotNone(result.projection_path)
        self.assertIn(
            ".docker-generated/runtime",
            result.projection_path,  # type: ignore[arg-type]
            "projection must be under .docker-generated/runtime/",
        )

    def test_projection_has_content_hash(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIsNotNone(result.projection_hash)
        self.assertEqual(len(result.projection_hash or ""), 64,  # type: ignore[arg-type]
                         "SHA-256 hash must be 64 hex chars")

    # ── read-only mount ──────────────────────────────────────────

    def test_projection_mounted_readonly(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        # Find the projection mount and verify 'readonly' is in the spec.
        proj_idx = _find_mount(
            result.run_args,
            dst="/run/pi-cli/docker-constructor.runtime.toml",
        )
        spec = result.run_args[proj_idx + 1]
        self.assertIn("readonly", spec,
                      "runtime projection must be mounted read-only")

    # ── gateway mapping ──────────────────────────────────────────

    def test_gateway_passed_to_add_host(self) -> None:
        """The persisted operational gateway must appear in
        ``--add-host`` exactly, not a default or fallback."""
        req = self._request(
            gateway="192.0.2.77",
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIn("--add-host", result.run_args)
        host_idx = result.run_args.index("--add-host")
        self.assertEqual(
            result.run_args[host_idx + 1],
            "host.docker.internal:192.0.2.77",
            "gateway must be used exactly, not silently defaulted",
        )

    # ── TTY modes ────────────────────────────────────────────────

    def test_tty_on_by_default(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIn("--tty", result.run_args)

    def test_tty_off_when_requested(self) -> None:
        req = self._request(
            tty=False,
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertNotIn("--tty", result.run_args)

    def test_interactive_on_by_default(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertIn("--interactive", result.run_args)

    def test_interactive_off_when_requested(self) -> None:
        req = self._request(
            stdin_open=False,
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertNotIn("--interactive", result.run_args)

    # ── pi-N allocation ──────────────────────────────────────────

    def test_container_name_allocated(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector({"pi-1", "pi-2"}),
        )
        result = self._run(req)
        self.assertEqual(result.container_name, "pi-3")
        name_idx = result.run_args.index("--name")
        self.assertEqual(result.run_args[name_idx + 1], "pi-3")

    def test_default_factory_creates_real_projection_and_cleans_up(self) -> None:
        """When no _create_projection is injected, the default
        factory must call the real create_runtime_projection and
        produce a handle whose path is under the repository-owned
        runtime directory.  The handle must clean up on exit."""
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
            _create_projection=None,
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        self.assertIsNotNone(result.projection_path)
        expected_prefix = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..",
                         ".docker-generated", "runtime"),
        )
        self.assertTrue(
            os.path.realpath(
                result.projection_path  # type: ignore[arg-type]
            ).startswith(expected_prefix),
            f"default factory path {result.projection_path!r} "
            f"must be under {expected_prefix!r}",
        )
        # The handle must have cleaned up on exit.
        self.assertFalse(
            os.path.exists(result.projection_path),  # type: ignore[arg-type]
            "default factory handle must remove projection after exit",
        )

    # ── dry-run ──────────────────────────────────────────────────

    def test_dry_run_produces_display_string(self) -> None:
        req = self._request(
            dry_run=True,
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        self.assertIsNotNone(result.display_string)
        self.assertIn("docker run", result.display_string or "")

    def test_dry_run_does_not_invoke_executor(self) -> None:
        req = self._request(
            dry_run=True,
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        # If any bomb exploded the test would have already failed.

    def test_dry_run_still_renders_args(self) -> None:
        req = self._request(
            dry_run=True,
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertTrue(len(result.run_args) > 0)

    # ── Docker failure ───────────────────────────────────────────

    def test_executor_nonzero_exit_is_operational_error(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=1),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.OPERATIONAL)
        self.assertIsNotNone(result.process_result)
        self.assertEqual(
            result.process_result.return_code, 1,  # type: ignore[union-attr]
        )

    def test_executor_raises_oserror(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(
                fail_with=OSError("docker not found"),
            ),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.OPERATIONAL)
        self.assertIn("docker not found", result.message or "")

    def test_executor_exception_mapped_not_propagated(self) -> None:
        """Unexpected executor exceptions (OSError, RuntimeError,
        etc.) must be mapped to an OPERATIONAL :class:`RunResult`,
        never propagated to the caller."""
        req = self._request(
            executor=FakeRunExecutor(
                fail_with=RuntimeError("unexpected crash"),
            ),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.OPERATIONAL,
            "unexpected executor exception must be mapped, not raised",
        )
        self.assertIsNotNone(result.message)

    # ── projection cleanup (recording factory) ───────────────────

    def test_projection_created_and_cleaned_up_on_success(self) -> None:
        """On success the projection handle must be entered (file
        created), then exited (file removed)."""
        factory = RecordingProjectionFactory()
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
            _create_projection=factory,
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.SUCCESS)
        self.assertEqual(len(factory.handles), 1)
        h = factory.handles[0]
        self.assertTrue(h.entered, "projection must be entered (file created)")
        self.assertTrue(h.exited, "projection must be exited (file removed)")
        self.assertFalse(
            os.path.exists(h.path),
            "projection file must be gone after success",
        )

    def test_projection_created_and_cleaned_up_on_nonzero_exit(self) -> None:
        """Docker non-zero exit → handle entered, exited, file gone."""
        factory = RecordingProjectionFactory()
        req = self._request(
            executor=FakeRunExecutor(returncode=1),
            inspector=FakeContainerNameInspector(set()),
            _create_projection=factory,
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.OPERATIONAL)
        self.assertEqual(len(factory.handles), 1)
        h = factory.handles[0]
        self.assertTrue(h.entered)
        self.assertTrue(h.exited)
        self.assertFalse(os.path.exists(h.path))

    def test_projection_created_and_cleaned_up_on_executor_oserror(self) -> None:
        """When the executor raises OSError the handle must still
        be exited and the file removed."""
        factory = RecordingProjectionFactory()
        req = self._request(
            executor=FakeRunExecutor(
                fail_with=OSError("docker not found"),
            ),
            inspector=FakeContainerNameInspector(set()),
            _create_projection=factory,
        )
        result = self._run(req)
        self.assertEqual(len(factory.handles), 1)
        h = factory.handles[0]
        self.assertTrue(h.entered)
        self.assertTrue(
            h.exited,
            "projection must be cleaned up even when executor raises OSError",
        )
        self.assertFalse(os.path.exists(h.path))

    def test_projection_created_and_cleaned_up_on_runtime_error(self) -> None:
        """When the executor raises an arbitrary RuntimeError the
        handle must still be exited and the file removed."""
        factory = RecordingProjectionFactory()
        req = self._request(
            executor=FakeRunExecutor(
                fail_with=RuntimeError("unexpected crash"),
            ),
            inspector=FakeContainerNameInspector(set()),
            _create_projection=factory,
        )
        result = self._run(req)
        self.assertEqual(len(factory.handles), 1)
        h = factory.handles[0]
        self.assertTrue(h.entered)
        self.assertTrue(
            h.exited,
            "projection must be cleaned up even on unexpected RuntimeError",
        )
        self.assertFalse(os.path.exists(h.path))

    def test_dry_run_creates_no_temporary_files(self) -> None:
        """Dry-run SHALL not create temporary configuration files.

        A bomb projection factory proves the orchestrator never
        attempts to create a projection — not even a create-then-
        delete cycle.  Bomb executor and inspector independently
        prove no Docker process is launched."""
        req = self._request(
            dry_run=True,
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        # If any bomb exploded the test would have already failed.
        # Additionally assert no projection path is reported as
        # an on-disk file.
        if result.projection_path is not None:
            self.assertFalse(
                os.path.exists(result.projection_path),
                "dry-run must not create projection files on disk",
            )

    # ── missing boundaries ───────────────────────────────────────

    def test_no_executor_and_not_dry_run_is_error(self) -> None:
        req = self._request(
            executor=None,
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.OPERATIONAL)
        self.assertIsNotNone(result.message)

    def test_no_inspector_is_error(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=None,
        )
        result = self._run(req)
        self.assertEqual(result.exit_kind, ExitKind.OPERATIONAL)
        self.assertIsNotNone(result.message)

    # ── runtime overrides ───────────────────────────────────────

    def test_valid_override_produces_success(self) -> None:
        """A recognised runtime override for an existing extension
        with a version that satisfies its policy must be accepted."""
        req = self._request(
            overrides={
                "runtime.pi-extensions.pi-read.version": "0.3.0",
            },
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.SUCCESS,
            f"valid override must succeed, got {result.exit_kind}: {result.message}",
        )

    def test_override_selects_alternate_artifact(self) -> None:
        """Overriding pi-read from the default 0.2.0 to 0.3.0 must
        produce a different projection than the default, proving the
        override reached artifact selection — not just no-op accepted."""
        # Default run (no overrides)
        default_result = self._run(self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        ))
        self.assertEqual(default_result.exit_kind, ExitKind.SUCCESS)

        # Overridden run
        overridden_result = self._run(self._request(
            overrides={
                "runtime.pi-extensions.pi-read.version": "0.3.0",
            },
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        ))
        self.assertEqual(overridden_result.exit_kind, ExitKind.SUCCESS)

        # The two projections must differ — different artifact selected.
        self.assertIsNotNone(default_result.projection_hash)
        self.assertIsNotNone(overridden_result.projection_hash)
        self.assertNotEqual(
            default_result.projection_hash,
            overridden_result.projection_hash,
            "override to alternate artifact must change the projection content",
        )

    def test_unknown_override_path_is_config_error(self) -> None:
        """An override path that does not match any known extension
        must be rejected before projection creation, Docker inspection,
        or Docker execution."""
        req = self._request(
            overrides={
                "runtime.pi-extensions.nonexistent.version": "1.0.0",
            },
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.CONFIG,
            f"unknown override must be CONFIG, got {result.exit_kind}",
        )
        # If any bomb exploded the test would have already failed.

    def test_build_scoped_override_rejected_in_run(self) -> None:
        """A build-scoped override path must not be accepted by
        the run transaction.  Validation must reject it before any
        side effect."""
        req = self._request(
            overrides={
                "build.stages.toolchain.python.version": "3.15.0",
            },
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.CONFIG,
            f"build override in run must be CONFIG, got {result.exit_kind}",
        )

    def test_override_version_not_in_catalog_is_config_error(self) -> None:
        """An override version that has no matching artifact catalog
        entry must be rejected before any side effect."""
        req = self._request(
            overrides={
                "runtime.pi-extensions.pi-read.version": "99.99.99",
            },
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.CONFIG,
            f"missing catalog entry must be CONFIG, got {result.exit_kind}",
        )

    def test_override_rejection_creates_no_projection(self) -> None:
        """When an override is rejected, the projection factory must
        never be called and no file must appear on disk."""
        req = self._request(
            overrides={
                "runtime.pi-extensions.nonexistent.version": "1.0.0",
            },
            executor=_BombExecutor(),
            inspector=_BombInspector(),
            _create_projection=_BombProjectionFactory(),
        )
        result = self._run(req)
        # If any bomb exploded the test would have already failed.
        if result.projection_path is not None:
            self.assertFalse(
                os.path.exists(result.projection_path),
                "rejected override must not create a projection file",
            )

    def test_default_no_overrides_produces_success(self) -> None:
        """With no overrides supplied, the default versions from
        the reviewed inventory must be used without error."""
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertEqual(
            result.exit_kind, ExitKind.SUCCESS,
            "default (no overrides) must succeed",
        )

    # ── projected paths are absolute ─────────────────────────────

    def test_projection_host_path_is_absolute(self) -> None:
        req = self._request(
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        self.assertTrue(
            (result.projection_path or "").startswith("/"),
            "projection path must be absolute",
        )

    def test_main_project_1to1_in_result(self) -> None:
        req = self._request(
            selection=ProjectSelection(
                main_project="/work/main",
                optional_projects=("/work/opt",),
            ),
            executor=FakeRunExecutor(returncode=0),
            inspector=FakeContainerNameInspector(set()),
        )
        result = self._run(req)
        # Main project mounted 1:1
        main_spec = _parse_mount_spec(result.run_args, dst="/work/main")
        self.assertEqual(main_spec["src"], "/work/main")
        # Optional project mounted 1:1
        opt_spec = _parse_mount_spec(result.run_args, dst="/work/opt")
        self.assertEqual(opt_spec["src"], "/work/opt")
        # Both exported
        self.assertIn("PROJECT_PATH_1=/work/main", result.run_args)
        self.assertIn("PROJECT_PATH_2=/work/opt", result.run_args)

    # ── projection readability before execution ──────────────────

    def test_projection_readable_before_docker_run(self) -> None:
        """Before ``docker run`` executes, the projection file must
        be world-readable (0444) so container-remapped users can
        access it via the bind-mount.

        Exercises the real :func:`create_runtime_projection` through
        a wrapping spy — the file on disk is created by the
        production code, not by a test double."""
        import os
        import stat

        from docker.versioning.effective import (
            _repo_runtime_dir,
            create_runtime_projection,
        )

        # The real factory validates the path is under the
        # repository-owned runtime directory and the renderer
        # requires the file live directly inside …/runtime/.
        import uuid
        real_parent = _repo_runtime_dir()
        unique_name = f"proj-{uuid.uuid4().hex}.toml"
        real_host_path = os.path.join(real_parent, unique_name)
        try:
            recorded: list[tuple[str, str]] = []  # (path, content_hash)
            observed_modes: list[int] = []

            class _WrappingFactory:
                """Spy that delegates to the real projection factory."""

                def __call__(self, projection: object, *,
                             parent_dir: str) -> Any:
                    handle = create_runtime_projection(
                        projection,
                        host_path=real_host_path,
                    )
                    recorded.append((handle.path, handle.content_hash))
                    return handle

            class _AssertingExecutor:
                def run(self, argv: tuple[str, ...]) -> Any:
                    for path, _ in recorded:
                        if os.path.exists(path):
                            mode = os.stat(path).st_mode & 0o777
                            observed_modes.append(mode)
                    from docker.launcher import ProcessResult
                    return ProcessResult(
                        argv=argv, return_code=0,
                        stdout="", stderr="",
                    )

            req = self._request(
                executor=_AssertingExecutor(),
                inspector=FakeContainerNameInspector(set()),
                _create_projection=_WrappingFactory(),
            )

            result = self._run(req)
            # Sanity: the wrapper was called and the executor ran.
            self.assertTrue(
                len(recorded) >= 1,
                "wrapping factory was not called — projection creation "
                "may have failed before execution",
            )
            self.assertTrue(
                len(observed_modes) >= 1,
                "executor was never reached — projection created but "
                "execution did not proceed",
            )
            for mode in observed_modes:
                self.assertEqual(
                    0o444, mode,
                    f"projection mode {oct(mode)} before docker run "
                    f"— expected 0o444 for remapped-container access",
                )
            # Content hash was recorded from the real factory.
            self.assertIsNotNone(recorded[0][1])
        finally:
            import shutil
            if os.path.exists(real_host_path):
                os.unlink(real_host_path)


# ═══════════════════════════════════════════════════════════════════
# 11.3 - Docker-backed boundaries (ProcessRunner injection)
# ═══════════════════════════════════════════════════════════════════


class TestDockerContainerInspector(unittest.TestCase):
    """Contract for :class:`DockerContainerInspector` — runs
    ``docker ps -a`` through an injected :class:`ProcessRunner`.
    All tests are daemon-independent."""

    def test_passes_correct_argv(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(
                argv=("docker", "ps", "-a", "--format", "{{.Names}}"),
                return_code=0,
                stdout="pi-1\npi-2\n",
            ),
        ])
        inspector = DockerContainerInspector(runner)
        names = inspector.list_names()
        self.assertEqual(names, {"pi-1", "pi-2"})
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(
            runner.calls[0],
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
        )

    def test_parses_docker_ps_output(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(
                argv=(),
                return_code=0,
                stdout="pi-1\npi-3\npi-7\n",
            ),
        ])
        inspector = DockerContainerInspector(runner)
        self.assertEqual(inspector.list_names(), {"pi-1", "pi-3", "pi-7"})

    def test_empty_output_no_containers(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(argv=(), return_code=0, stdout=""),
        ])
        inspector = DockerContainerInspector(runner)
        self.assertEqual(inspector.list_names(), set())

    def test_whitespace_only_output(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(argv=(), return_code=0, stdout="\n  \n"),
        ])
        inspector = DockerContainerInspector(runner)
        self.assertEqual(inspector.list_names(), set())

    def test_docker_unavailable_raises_inspect_error(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(
                argv=(),
                return_code=1,
                stderr="Cannot connect to the Docker daemon",
            ),
        ])
        inspector = DockerContainerInspector(runner)
        with self.assertRaises(ContainerInspectError):
            inspector.list_names()

    def test_process_runner_oserror_wrapped_as_inspect_error(self) -> None:
        """ContainerNameInspector promises ContainerInspectError when
        Docker is unavailable.  Raw OSError from the process runner
        must be caught and wrapped so callers only handle the
        documented domain error."""
        class BrokenRunner(ProcessRunner):
            def run(self, argv: list[str]) -> ProcessResult:
                raise OSError("docker not found")

        inspector = DockerContainerInspector(BrokenRunner())
        with self.assertRaises(ContainerInspectError) as ctx:
            inspector.list_names()
        self.assertIn("docker not found", str(ctx.exception))

    def test_duplicate_names_in_output(self) -> None:
        """If docker ps returns duplicates, they collapse to a single set entry."""
        runner = FakeProcessRunner([
            ProcessResult(
                argv=(),
                return_code=0,
                stdout="pi-1\npi-1\npi-2\n",
            ),
        ])
        inspector = DockerContainerInspector(runner)
        self.assertEqual(inspector.list_names(), {"pi-1", "pi-2"})


class TestDockerRunExecutor(unittest.TestCase):
    """Contract for :class:`DockerRunExecutor` — passes the rendered
    ``docker`` argument vector through an injected
    :class:`ProcessRunner`.  All tests are daemon-independent."""

    def test_passes_argv_through_to_runner(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(
                argv=("docker", "run", "--rm", "alpine"),
                return_code=0,
            ),
        ])
        executor = DockerRunExecutor(runner)
        result = executor.run(("docker", "run", "--rm", "alpine"))
        self.assertEqual(result.return_code, 0)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(
            runner.calls[0],
            ["docker", "run", "--rm", "alpine"],
        )

    def test_returns_process_result_unchanged(self) -> None:
        canned = ProcessResult(
            argv=("docker", "run", "img"),
            return_code=0,
            stdout="hello",
            stderr="",
        )
        runner = FakeProcessRunner([canned])
        executor = DockerRunExecutor(runner)
        result = executor.run(("docker", "run", "img"))
        self.assertEqual(result.argv, ("docker", "run", "img"))
        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.stdout, "hello")
        self.assertEqual(result.stderr, "")

    def test_nonzero_exit_preserved(self) -> None:
        runner = FakeProcessRunner([
            ProcessResult(
                argv=("docker", "run", "bad"),
                return_code=127,
                stderr="image not found",
            ),
        ])
        executor = DockerRunExecutor(runner)
        result = executor.run(("docker", "run", "bad"))
        self.assertEqual(result.return_code, 127)
        self.assertIn("image not found", result.stderr)

    def test_process_runner_oserror_propagates(self) -> None:
        class BrokenRunner(ProcessRunner):
            def run(self, argv: list[str]) -> ProcessResult:
                raise OSError("docker not found")

        executor = DockerRunExecutor(BrokenRunner())
        with self.assertRaises(OSError):
            executor.run(("docker", "run", "img"))


if __name__ == "__main__":
    unittest.main()
