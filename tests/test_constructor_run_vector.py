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
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/proj.toml"
            ),
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        )
        mounts = _collect_mounts(args)
        proj = _find_mount(mounts, dst="/run/pi-cli/docker-constructor.runtime.toml")
        self.assertIsNotNone(proj, "missing runtime projection mount")
        self.assertEqual(
            proj["src"],
            "/home/dev/.pi-cli/.docker-generated/runtime/proj.toml",
        )

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
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/launch-a.toml"
            ),
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
        )
        b = _render(
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/launch-b.toml"
            ),
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
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/x.toml"
            ),
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
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/x.toml"
            ),
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            pi_home_host="/home/alice/.pi",
            main_project="/home/dev/work/main",
        ))
        b = render_run_vector(RunRenderInputs(
            main_project="/home/dev/work/main",
            pi_home_host="/home/alice/.pi",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/x.toml"
            ),
            container_name="pi-1",
            image="pi-cli-pi:latest",
        ))
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# 6.3  Edge-case and security tests
# ---------------------------------------------------------------------------


class TestPathEdgeCases(unittest.TestCase):
    """Paths with spaces, quotes, Unicode, and leading dashes must be
    preserved as individual vector elements."""

    def test_project_path_with_spaces(self):
        args = _render(main_project="/home/dev/work/my project")
        self.assertIn("/home/dev/work/my project", args)
        mounts = _collect_mounts(args)
        main = _find_mount(mounts, dst="/home/dev/work/my project")
        self.assertIsNotNone(main)
        self.assertEqual(main["src"], "/home/dev/work/my project")

    def test_project_path_with_unicode(self):
        path = "/home/dev/work/projéct-α"
        args = _render(main_project=path)
        env = _collect_env(args)
        self.assertEqual(env["PROJECT_PATH_1"], path)

    def test_project_path_with_leading_dashes(self):
        """A path like /home/dev/--help must not be misinterpreted
        as a Docker flag — it's a positional argument value."""
        path = "/home/dev/work/--project-name"
        args = _render(main_project=path)
        # The path must appear verbatim after --workdir and as PROJECT_PATH_1.
        wd_idx = args.index("--workdir")
        self.assertEqual(args[wd_idx + 1], path)
        env = _collect_env(args)
        self.assertEqual(env["PROJECT_PATH_1"], path)

    def test_pi_home_host_with_spaces(self):
        args = _render(pi_home_host="/home/user name/.pi")
        mounts = _collect_mounts(args)
        from docker.versioning.rendering import _CONTAINER_PI_HOME
        pi = _find_mount(mounts, dst=_CONTAINER_PI_HOME)
        self.assertIsNotNone(pi)
        self.assertEqual(pi["src"], "/home/user name/.pi")


class TestProjectValidation(unittest.TestCase):
    """Reject malformed project inputs."""

    def test_empty_main_project_rejected(self):
        with self.assertRaises(ValueError):
            _render(main_project="")

    def test_whitespace_only_main_project_rejected(self):
        with self.assertRaises(ValueError):
            _render(main_project="   ")

    def test_empty_optional_project_entry_rejected(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/main",
                optional_projects=("/home/dev/work/opt1", ""),
            )

    def test_duplicate_project_paths_rejected(self):
        """A path appearing as both main and optional project must
        be rejected — duplicate mounts would collide."""
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/shared",
                optional_projects=("/home/dev/work/other", "/home/dev/work/shared"),
            )

    def test_duplicate_optional_project_paths_rejected(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/main",
                optional_projects=("/home/dev/work/opt1", "/home/dev/work/opt1"),
            )

    def test_more_than_two_optional_projects_accepted(self) -> None:
        """Direct Docker execution has no limit on optional projects
        (the old 2-project limit was a Compose fragment artefact)."""
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=(
                "/home/dev/work/opt1",
                "/home/dev/work/opt2",
                "/home/dev/work/opt3",
            ),
        )
        # All three optionals must appear as 1:1 mounts
        args_str = " ".join(args)
        self.assertIn("dst=/home/dev/work/opt1", args_str)
        self.assertIn("dst=/home/dev/work/opt2", args_str)
        self.assertIn("dst=/home/dev/work/opt3", args_str)
        # All three exported as PROJECT_PATH_2,3,4
        self.assertIn("PROJECT_PATH_1=/home/dev/work/main", args)
        self.assertIn("PROJECT_PATH_2=/home/dev/work/opt1", args)
        self.assertIn("PROJECT_PATH_3=/home/dev/work/opt2", args)
        self.assertIn("PROJECT_PATH_4=/home/dev/work/opt3", args)

    def test_relative_main_project_rejected(self):
        with self.assertRaises(ValueError):
            _render(main_project="relative/path/project")

    def test_relative_optional_project_rejected(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/main",
                optional_projects=("relative/path/project",),
            )

    def test_relative_pi_home_host_rejected(self):
        with self.assertRaises(ValueError):
            _render(pi_home_host="~/.pi")


class TestImageAndNameValidation(unittest.TestCase):
    """Reject invalid image tags and container names."""

    def test_empty_image_rejected(self):
        with self.assertRaises(ValueError):
            _render(image="")

    def test_whitespace_image_rejected(self):
        with self.assertRaises(ValueError):
            _render(image="   ")

    def test_empty_container_name_rejected(self):
        with self.assertRaises(ValueError):
            _render(container_name="")

    def test_whitespace_container_name_rejected(self):
        with self.assertRaises(ValueError):
            _render(container_name="  ")


class TestMountSecurity(unittest.TestCase):
    """Reject mounts that would leak host-only metadata into the
    container or conflict with expected destinations."""

    def test_writable_projection_mount_rejected(self):
        """The runtime projection mount must be read-only.
        There is no API to request a writable projection — the
        renderer enforces it unconditionally."""
        args = _render()
        mounts = _collect_mounts(args)
        proj = _find_mount(mounts,
                           dst="/run/pi-cli/docker-constructor.runtime.toml")
        self.assertIsNotNone(proj)
        # readonly may be "true" or present as a key with empty value.
        # Either way, it signals read-only.
        self.assertIn("readonly", proj,
                      "projection mount must be read-only")
        self.assertNotEqual(proj.get("readonly", "true"), "false",
                            "projection mount must not be writable")

    def test_docker_constructor_toml_as_projection_rejected(self):
        """Passing docker-constructor.toml as projection_host_path
        must be rejected — the reviewed source must not leak into
        the container."""
        with self.assertRaises(ValueError):
            _render(
                projection_host_path=(
                    "/home/dev/.pi-cli/docker-constructor.toml"
                ),
            )

    def test_effective_build_projection_as_projection_rejected(self):
        """The effective build projection file must not be mounted
        into the runtime container."""
        with self.assertRaises(ValueError):
            _render(
                projection_host_path=(
                    "/home/dev/.pi-cli/.docker-generated/"
                    "docker-constructor.build.effective.toml"
                ),
            )

    def test_broad_dot_docker_generated_as_projection_rejected(self):
        """.docker-generated/ as a directory must not be mounted —
        only individual files under .docker-generated/runtime/ are
        valid projection paths."""
        with self.assertRaises(ValueError):
            _render(
                projection_host_path=(
                    "/home/dev/.pi-cli/.docker-generated"
                ),
            )

    def test_projection_path_outside_runtime_dir_rejected(self):
        """The host projection path must reside under
        .docker-generated/runtime/."""
        with self.assertRaises(ValueError):
            _render(projection_host_path="/tmp/outside-proj.toml")

    def test_false_positive_substring_rejected(self):
        """A path whose string contains '.docker-generated/runtime/'
        but not as actual directory components must be rejected.
        E.g. /tmp/not.docker-generated/runtime/file.toml is a sibling
        directory, not a child of .docker-generated/."""
        with self.assertRaises(ValueError):
            _render(
                projection_host_path=(
                    "/tmp/not.docker-generated/runtime/file.toml"
                ),
            )

    def test_relative_projection_host_path_rejected(self):
        """A relative projection path must be rejected — the caller
        must supply an absolute path."""
        with self.assertRaises(ValueError):
            _render(
                projection_host_path=(
                    ".docker-generated/runtime/proj.toml"
                ),
            )

    def test_noncanonical_projection_container_path_rejected(self):
        """The container-side projection destination is fixed at
        ``/run/pi-cli/docker-constructor.runtime.toml``.  Passing any
        other path must be rejected."""
        with self.assertRaises(ValueError):
            _render(
                projection_container_path="/etc/evil.toml",
            )

    def test_canonical_projection_container_path_accepted(self):
        """The fixed path must be accepted (sanity check — the
        default helper already uses this value)."""
        _render(
            projection_container_path=(
                "/run/pi-cli/docker-constructor.runtime.toml"
            ),
        )

    def test_projection_path_in_runtime_dir_accepted(self):
        """Paths under .docker-generated/runtime/ are valid."""
        # This must not raise.
        _render(
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/proj-abc123.toml"
            ),
        )


class TestDestinationCollisions(unittest.TestCase):
    """Reject mount destination collisions across the complete
    destination set before rendering."""

    def test_main_project_collides_with_pi_home(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/.pi",
                pi_home_host="/home/alice/.pi",
            )

    def test_optional_project_collides_with_pi_home(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/main",
                optional_projects=("/home/dev/.pi",),
                pi_home_host="/home/alice/.pi",
            )

    def test_main_project_collides_with_projection_dst(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/run/pi-cli/docker-constructor.runtime.toml",
            )

    def test_optional_project_collides_with_projection_dst(self):
        with self.assertRaises(ValueError):
            _render(
                main_project="/home/dev/work/main",
                optional_projects=(
                    "/run/pi-cli/docker-constructor.runtime.toml",
                ),
            )

    def test_no_collision_between_pi_home_and_projection(self):
        """Pi home dst (/home/dev/.pi) and projection dst
        (/run/pi-cli/...) are distinct — must not raise."""
        _render(
            pi_home_host="/home/alice/.pi",
            projection_container_path=(
                "/run/pi-cli/docker-constructor.runtime.toml"
            ),
        )


class TestDeterministicOrderingEdge(unittest.TestCase):
    """Deterministic output independent of input field order."""

    def test_optional_projects_in_order(self):
        """Optional projects must appear in the vector in the order
        they were given — no sorting or reordering."""
        a = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/B", "/home/dev/work/A"),
        )
        b = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/A", "/home/dev/work/B"),
        )
        # Different input order → different vector (caller controls ordering).
        self.assertNotEqual(a, b)

    def test_flag_order_deterministic(self):
        """Calling render_run_vector twice with identical RunRenderInputs
        constructed with different kwarg order must produce the same
        flag order in the output vector."""
        a = render_run_vector(RunRenderInputs(
            image="pi-cli-pi:latest",
            container_name="pi-1",
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/x.toml"
            ),
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            pi_home_host="/home/alice/.pi",
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/lib",),
        ))
        b = render_run_vector(RunRenderInputs(
            optional_projects=("/home/dev/work/lib",),
            main_project="/home/dev/work/main",
            pi_home_host="/home/alice/.pi",
            projection_container_path="/run/pi-cli/docker-constructor.runtime.toml",
            projection_host_path=(
                "/home/dev/.pi-cli/.docker-generated/runtime/x.toml"
            ),
            container_name="pi-1",
            image="pi-cli-pi:latest",
        ))
        self.assertEqual(a, b,
                         "output must be independent of RunRenderInputs kwarg order")


class TestArgumentAtomicity(unittest.TestCase):
    """No argument may contain shell-joined command text."""

    def test_no_shell_joined_flags(self):
        """Every --flag and its value are separate elements.
        No '--flag=value' or '--flag value' fused into one string."""
        args = _render(
            main_project="/home/dev/work/main",
            optional_projects=("/home/dev/work/lib",),
        )
        for token in args:
            if token.startswith("--"):
                self.assertNotIn("=", token,
                                 f"flag {token!r} must not embed its value")
                self.assertNotIn(" ", token,
                                 f"flag {token!r} must not embed its value")

    def test_no_env_with_equals_in_key(self):
        """--env KEY=VALUE must be two tokens: --env and KEY=VALUE."""
        args = _render()
        # The --env token itself must be bare.
        for i, token in enumerate(args):
            if token == "--env":
                self.assertLess(i + 1, len(args))
                self.assertFalse(args[i + 1].startswith("--"),
                                 f"--env followed by flag {args[i+1]!r}")


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


# ── 6.6 architectural guards ──────────────────────────────────────

class TestArchitecturalGuards(unittest.TestCase):
    """New direct-Docker renderers must not depend on process
    environment, must return ``tuple[str, ...]``, and must never
    emit ``docker compose``."""

    def test_result_is_always_tuple(self):
        result = _render()
        self.assertIsInstance(result, tuple)
        self.assertTrue(all(isinstance(t, str) for t in result))

    def test_environment_does_not_affect_output(self):
        import os as _os
        baseline = _render()
        saved = {}
        for k in ("COMPOSE_FILE", "DOCKER_HOST", "PI_PROJECT_DIR",
                  "HOME", "USER", "PI_HOME", "DOCKER_RUN_OPTS"):
            saved[k] = _os.environ.get(k)
            _os.environ[k] = f"injected-{k}-value"
        try:
            self.assertEqual(_render(), baseline)
        finally:
            for k, v in saved.items():
                if v is None:
                    _os.environ.pop(k, None)
                else:
                    _os.environ[k] = v

    def test_vector_never_contains_compose(self):
        result = _render()
        self.assertNotIn("compose", result)
        self.assertEqual(result[0], "docker")
        self.assertEqual(result[1], "run")

    # ── 6.7 projection-origin tests ───────────────────────────────

    def test_run_renderer_never_inspects_runtime_dto_contents(self):
        """The run renderer mounts the runtime projection file but
        never opens, reads, or parses it.  It only uses the host path
        for the ``--mount`` argument — the contents are the container's
        responsibility."""
        # The renderer accepts arbitrary host paths (validated only
        # for directory structure, not file existence).  A path to a
        # nonexistent or empty file must not cause a read/parse error.
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as td:
            runtime_dir = _os.path.join(td, ".docker-generated", "runtime")
            _os.makedirs(runtime_dir)
            # Create an empty file — the renderer must not attempt to read it
            empty_path = _os.path.join(runtime_dir, "empty.toml")
            with open(empty_path, "w") as f:
                f.write("")
            args = _render(
                projection_host_path=empty_path,
            )
            # The path must appear verbatim in a mount argument
            mounts = _collect_mounts(args)
            projection_mounts = [
                m for m in mounts
                if m["dst"] == "/run/pi-cli/docker-constructor.runtime.toml"
            ]
            self.assertEqual(
                len(projection_mounts), 1,
                "Runtime projection must be mounted exactly once"
            )
            self.assertEqual(projection_mounts[0]["src"], empty_path)
