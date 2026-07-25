"""Focused renderer tests for Stage 6.2 — Run command-vector rendering.

Tests ``render_run_vector`` against ``RunRenderInputs``.
No Docker, no network, no subprocess, no filesystem.
"""

from __future__ import annotations

import unittest

from docker.versioning.rendering import (
    RunRenderInputs,
    render_run_vector,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _render(*,
            image: str = "pi-cli-pi:latest",
            container_name: str = "pi-1",
            projection_host_path: str = "/home/dev/.pi-cli/.docker-generated/runtime/proj-abc123.toml",
            projection_container_path: str = "/run/pi-cli/docker-constructor.runtime.toml",
            pi_home_host: str = "/home/alice/.pi",
            main_project: str = "/home/dev/work/my-project",
            optional_projects: tuple[str, ...] = (),
            gateway: str = "host-gateway",
            tty: bool = True,
            stdin_open: bool = True,
            command: tuple[str, ...] = (),
            chown_on_start: str | None = None,
            ) -> tuple[str, ...]:
    return render_run_vector(RunRenderInputs(
        image=image,
        container_name=container_name,
        projection_host_path=projection_host_path,
        projection_container_path=projection_container_path,
        pi_home_host=pi_home_host,
        main_project=main_project,
        optional_projects=optional_projects,
        gateway=gateway,
        tty=tty,
        stdin_open=stdin_open,
        command=command,
        chown_on_start=chown_on_start,
    ))


# ---------------------------------------------------------------------------
# 6.2.1  Default run vector shape
# ---------------------------------------------------------------------------


class TestDefaultRunVector(unittest.TestCase):
    """Assert the exact tuple shape for a default main-project launch."""

    def test_command_prefix_is_docker_run(self):
        args = _render()
        self.assertEqual(args[:2], ("docker", "run"),
                         "prefix must be 'docker run', never 'docker compose'")

    def test_no_compose_in_output(self):
        args = _render()
        self.assertNotIn("compose", args)
        self.assertNotIn("docker-compose", args)

    def test_flag_rm_present(self):
        args = _render()
        self.assertIn("--rm", args)

    def test_deterministic_container_name(self):
        args = _render(container_name="pi-session-1")
        idx = args.index("--name")
        self.assertEqual(args[idx + 1], "pi-session-1")

    def test_interactive_and_tty_by_default(self):
        args = _render()
        self.assertIn("--interactive", args)
        self.assertIn("--tty", args)

    def test_short_flags_not_used(self):
        """render_run_vector must use long-form flags (-i → --interactive,
        -t → --tty) so the vector is self-documenting."""
        args = _render()
        self.assertNotIn("-i", args)
        self.assertNotIn("-t", args)


# ---------------------------------------------------------------------------
# 6.2.2  Mounts — Pi home, projection, projects
# ---------------------------------------------------------------------------


class TestMounts(unittest.TestCase):
    """Assert Pi home, runtime projection, and project bind mounts."""

    def test_pi_home_mount(self):
        from docker.versioning.rendering import _CONTAINER_PI_HOME
        args = _render(pi_home_host="/home/alice/.pi")
        mounts = _collect_mounts(args)
        pi_mount = _find_mount(mounts, dst=_CONTAINER_PI_HOME)
        self.assertIsNotNone(pi_mount, "missing Pi home mount")
        self.assertEqual(pi_mount["src"], "/home/alice/.pi")
        self.assertNotEqual(pi_mount["src"], pi_mount["dst"],
                            "Pi home mount must map host ~/.pi to "
                            f"fixed container path {_CONTAINER_PI_HOME}")

    def test_pi_home_asymmetric_mount(self):
        """/home/bob/.pi on the host maps to /home/dev/.pi in the
        container — regardless of host username."""
        from docker.versioning.rendering import _CONTAINER_PI_HOME
        args = _render(pi_home_host="/home/bob/.pi")
        mounts = _collect_mounts(args)
        pi_mount = _find_mount(mounts, dst=_CONTAINER_PI_HOME)
        self.assertIsNotNone(pi_mount)
        self.assertEqual(pi_mount["src"], "/home/bob/.pi")
        self.assertEqual(pi_mount["dst"], "/home/dev/.pi")

    def test_runtime_projection_mount_present(self):
        args = _render(
            projection_host_path="/tmp/runtime/proj.toml",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        )
        mounts = _collect_mounts(args)
        proj = _find_mount(mounts, dst="/run/pi-cli/docker-constructor.runtime.toml")
        self.assertIsNotNone(proj, "missing runtime projection mount")
        self.assertEqual(proj["src"], "/tmp/runtime/proj.toml")

    def test_runtime_projection_mount_is_readonly(self):
        args = _render()
        mounts = _collect_mounts(args)
        proj = _find_mount(mounts, dst="/run/pi-cli/docker-constructor.runtime.toml")
        self.assertIsNotNone(proj)
        self.assertIn("readonly", proj,
                      "projection mount must be read-only")

    def test_runtime_projection_fixed_container_path(self):
        """The container-side path is fixed regardless of host path."""
        a = _render(
            projection_host_path="/tmp/launch-a.toml",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        )
        b = _render(
            projection_host_path="/tmp/launch-b.toml",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        )
        mount_a = _find_mount(_collect_mounts(a),
                              dst="/run/pi-cli/docker-constructor.runtime.toml")
        mount_b = _find_mount(_collect_mounts(b),
                              dst="/run/pi-cli/docker-constructor.runtime.toml")
        self.assertEqual(mount_a["dst"], mount_b["dst"])
        self.assertNotEqual(mount_a["src"], mount_b["src"])

    def test_main_project_1to1_bind_mount(self):
        args = _render(main_project="/home/dev/work/app")
        mounts = _collect_mounts(args)
        main = _find_mount(mounts, dst="/home/dev/work/app")
        self.assertIsNotNone(main, "missing main project mount")
        self.assertEqual(main["src"], "/home/dev/work/app")

    def test_main_project_as_workdir(self):
        args = _render(main_project="/home/dev/work/app")
        idx = args.index("--workdir")
        self.assertEqual(args[idx + 1], "/home/dev/work/app")


# ---------------------------------------------------------------------------
# 6.2.3  Environment variables
# ---------------------------------------------------------------------------


class TestEnvironment(unittest.TestCase):
    """Assert PROJECT_PATH_* and CHOWN_WORK_ON_START environment."""

    def test_project_path_1_set(self):
        args = _render(main_project="/home/dev/work/app")
        env = _collect_env(args)
        self.assertEqual(env.get("PROJECT_PATH_1"), "/home/dev/work/app")

    def test_chown_on_start_when_set(self):
        args = _render(chown_on_start="1")
        env = _collect_env(args)
        self.assertEqual(env.get("CHOWN_WORK_ON_START"), "1")

    def test_no_chown_on_start_when_none(self):
        args = _render(chown_on_start=None)
        env = _collect_env(args)
        self.assertNotIn("CHOWN_WORK_ON_START", env)


# ---------------------------------------------------------------------------
# 6.2.4  Gateway mapping
# ---------------------------------------------------------------------------


class TestGatewayMapping(unittest.TestCase):
    """Assert --add-host for host.docker.internal."""

    def test_gateway_host_gateway(self):
        args = _render(gateway="host-gateway")
        self.assertIn("--add-host", args)
        idx = args.index("--add-host")
        self.assertEqual(args[idx + 1], "host.docker.internal:host-gateway")

    def test_gateway_explicit_ip(self):
        args = _render(gateway="10.0.2.2")
        idx = args.index("--add-host")
        self.assertEqual(args[idx + 1], "host.docker.internal:10.0.2.2")


# ---------------------------------------------------------------------------
# 6.2.5  Canonical image and command passthrough
# ---------------------------------------------------------------------------


class TestImageAndCommand(unittest.TestCase):
    """Assert canonical image placement and command passthrough."""

    def test_canonical_image_is_last_before_command(self):
        args = _render(image="pi-cli-pi:latest")
        # Image appears after all flags and before any passthrough command.
        idx = args.index("pi-cli-pi:latest")
        # No flag after the image.
        for token in args[idx + 1:]:
            self.assertFalse(token.startswith("--"),
                             f"flag {token!r} appears after image")

    def test_command_passthrough_after_image(self):
        args = _render(command=("bash", "-c", "echo hello"))
        img_idx = args.index("pi-cli-pi:latest")
        self.assertEqual(args[img_idx + 1:], ("bash", "-c", "echo hello"))

    def test_no_command_passthrough_when_empty(self):
        args = _render(command=())
        # Image is the last element.
        self.assertEqual(args[-1], "pi-cli-pi:latest")


# ---------------------------------------------------------------------------
# 6.2.6  Optional projects
# ---------------------------------------------------------------------------


class TestOptionalProjects(unittest.TestCase):
    """Assert one and two optional projects receive 1:1 mounts and
    ordered PROJECT_PATH_* variables."""

    def test_one_optional_project_mount(self):
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/opt1",),
        )
        mounts = _collect_mounts(args)
        opt = _find_mount(mounts, dst="/home/dev/work/opt1")
        self.assertIsNotNone(opt, "missing optional project mount")
        self.assertEqual(opt["src"], "/home/dev/work/opt1")

    def test_one_optional_project_env(self):
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/opt1",),
        )
        env = _collect_env(args)
        self.assertEqual(env["PROJECT_PATH_1"], "/home/dev/work/main")
        self.assertEqual(env["PROJECT_PATH_2"], "/home/dev/work/opt1")
        self.assertNotIn("PROJECT_PATH_3", env)

    def test_two_optional_projects_mounts(self):
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/opt1", "/home/dev/work/opt2"),
        )
        mounts = _collect_mounts(args)
        self.assertIsNotNone(_find_mount(mounts, dst="/home/dev/work/opt1"))
        self.assertIsNotNone(_find_mount(mounts, dst="/home/dev/work/opt2"))

    def test_two_optional_projects_env(self):
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/opt1", "/home/dev/work/opt2"),
        )
        env = _collect_env(args)
        self.assertEqual(env["PROJECT_PATH_1"], "/home/dev/work/main")
        self.assertEqual(env["PROJECT_PATH_2"], "/home/dev/work/opt1")
        self.assertEqual(env["PROJECT_PATH_3"], "/home/dev/work/opt2")


# ---------------------------------------------------------------------------
# 6.2.7  TTY / non-TTY modes
# ---------------------------------------------------------------------------


class TestTTYModes(unittest.TestCase):
    """Assert interactive (TTY) and non-TTY automation modes."""

    def test_interactive_mode_includes_tty_and_interactive(self):
        args = _render(tty=True, stdin_open=True)
        self.assertIn("--tty", args)
        self.assertIn("--interactive", args)

    def test_automation_mode_no_tty(self):
        args = _render(tty=False, stdin_open=False)
        self.assertNotIn("--tty", args)
        self.assertNotIn("--interactive", args)

    def test_stdin_open_without_tty(self):
        """--interactive without --tty: pipe mode (e.g. echo | docker run -i)."""
        args = _render(tty=False, stdin_open=True)
        self.assertNotIn("--tty", args)
        self.assertIn("--interactive", args)

    def test_tty_without_stdin_omits_both(self):
        """--tty without stdin_open: unusual but valid.  --tty enables
        Docker's TTY allocation which requires stdin to be meaningful."""
        args = _render(tty=True, stdin_open=False)
        # With tty=True, Docker typically needs --interactive too for
        # the TTY to be useful.  For now, render --tty alone.
        self.assertIn("--tty", args)
        self.assertNotIn("--interactive", args)


# ---------------------------------------------------------------------------
# 6.2.8  Command arguments with spaces and shell metacharacters
# ---------------------------------------------------------------------------


class TestCommandSpacesAndMetacharacters(unittest.TestCase):
    """Command arguments containing spaces or shell metacharacters
    must remain individual vector elements — no shell quoting needed."""

    def test_command_with_spaces(self):
        """Each argument is a separate string even when it contains
        internal spaces — subprocess passes them verbatim."""
        args = _render(command=("echo", "hello world", "foo bar"))
        img_idx = args.index("pi-cli-pi:latest")
        tail = args[img_idx + 1:]
        self.assertEqual(tail, ("echo", "hello world", "foo bar"))

    def test_command_with_dollar_sign(self):
        args = _render(command=("bash", "-c", "echo $HOME"))
        img_idx = args.index("pi-cli-pi:latest")
        tail = args[img_idx + 1:]
        self.assertEqual(tail, ("bash", "-c", "echo $HOME"))

    def test_command_with_semicolon(self):
        args = _render(command=("sh", "-c", "echo a; echo b"))
        img_idx = args.index("pi-cli-pi:latest")
        tail = args[img_idx + 1:]
        self.assertEqual(tail, ("sh", "-c", "echo a; echo b"))


# ---------------------------------------------------------------------------
# 6.2.9  Deterministic byte-for-byte output
# ---------------------------------------------------------------------------


class TestDeterministicOutput(unittest.TestCase):
    """Equivalent inputs produce byte-for-byte identical vectors."""

    def test_same_inputs_produce_identical_vector(self):
        ri = RunRenderInputs(
            image="pi-cli-pi:latest",
            container_name="pi-1",
            projection_host_path="/tmp/x.toml",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            pi_home_host="/home/alice/.pi",
            main_project="/home/dev/work/main",
        )
        a = render_run_vector(ri)
        b = render_run_vector(ri)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_different_kwarg_order_same_result(self):
        a = render_run_vector(RunRenderInputs(
            image="pi-cli-pi:latest",
            container_name="pi-1",
            projection_host_path="/tmp/x.toml",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            pi_home_host="/home/alice/.pi",
            main_project="/home/dev/work/main",
        ))
        b = render_run_vector(RunRenderInputs(
            main_project="/home/dev/work/main",
            pi_home_host="/home/alice/.pi",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            projection_host_path="/tmp/x.toml",
            container_name="pi-1",
            image="pi-cli-pi:latest",
        ))
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Argument-parsing helpers
# ---------------------------------------------------------------------------


def _collect_mounts(args: tuple[str, ...]) -> list[dict[str, str]]:
    """Extract all ``--mount`` key=value,... specs into dicts."""
    mounts: list[dict[str, str]] = []
    it = iter(args)
    for token in it:
        if token == "--mount":
            raw = next(it)
            kv: dict[str, str] = {}
            for pair in raw.split(","):
                k, _, v = pair.partition("=")
                kv[k] = v
            mounts.append(kv)
    return mounts


def _find_mount(mounts: list[dict[str, str]],
                dst: str) -> dict[str, str] | None:
    for m in mounts:
        if m.get("dst") == dst:
            return m
    return None


def _collect_env(args: tuple[str, ...]) -> dict[str, str]:
    """Extract all ``--env KEY=VALUE`` pairs into a dict."""
    env: dict[str, str] = {}
    it = iter(args)
    for token in it:
        if token == "--env":
            raw = next(it)
            k, _, v = raw.partition("=")
            env[k] = v
    return env
