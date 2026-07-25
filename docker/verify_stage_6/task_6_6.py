#!/usr/bin/env python3
"""Run final Stage 6 validation and negative Docker tests for task 6.6."""
from __future__ import annotations
import argparse
from pathlib import Path
try:
    from .evidence import (EvidenceCollector, EvidenceRunError, compose_command,
                           prepare_pi_home, repo_root, resolved_env)
except ImportError:
    from evidence import (EvidenceCollector, EvidenceRunError, compose_command,
                          prepare_pi_home, repo_root, resolved_env)


def main(argv=None) -> int:
    root = repo_root(__file__)
    p = argparse.ArgumentParser()
    p.add_argument("--image", default="pi-cli-pi:latest")
    p.add_argument("--inventory", type=Path, default=Path(".docker-generated/docker-constructor.toml"))
    p.add_argument(
        "--bad-checksum-inventory", type=Path,
        default=Path("docker/verify_stage_6/inputs/bad-rtk-sha256.toml"),
    )
    p.add_argument(
        "--bad-base-digest-inventory", type=Path,
        default=Path("docker/verify_stage_6/inputs/bad-node-digest.toml"),
    )
    p.add_argument("--custom-uid", type=int, default=12345)
    p.add_argument("--custom-gid", type=int, default=12345)
    p.add_argument("--pi-home", type=Path)
    p.add_argument("--skip-extension-install", action="store_true")
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-stage6/6.6"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    ev = EvidenceCollector(args.output_dir, dry_run=args.dry_run)
    ok = False
    try:
        ev.run("provider-tests", ["python3", "-m", "unittest", "discover", "-s", "tests/versioning/providers", "-p", "test_*.py", "-q"], cwd=root)
        ev.run("version-tests", ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_version*.py", "-q"], cwd=root)
        ev.run("compileall", ["python3", "-m", "compileall", "-q", "docker", "tests", "launch-pi.py"], cwd=root)
        ev.run("default-build", compose_command("--progress", "plain", "build", "pi"), cwd=root, timeout=7200)
        ev.run("verify-runtime", ["sh", "docker/verify-runtime.sh", args.image], cwd=root, timeout=900)
        owns_pi_home = args.pi_home is None
        pi_home = args.pi_home or (args.output_dir / "pi-home")
        if not args.skip_extension_install:
            pi_home = prepare_pi_home(
                ev, root=root, image=args.image, path=pi_home, reset=owns_pi_home,
            )
        acceptance = ["python3", "docker/verify_versioned_image.py", "--image", args.image,
                      "--inventory", str(args.inventory), "--pi-home", str(pi_home)]
        ev.run("acceptance", acceptance, cwd=root, timeout=900)

        ev.expect_failure("bad-checksum-build", compose_command("--progress", "plain", "build", "pi",
                          inventory=args.bad_checksum_inventory), cwd=root, timeout=7200)
        ev.expect_failure("bad-base-digest-build", compose_command("--progress", "plain", "build", "pi",
                          inventory=args.bad_base_digest_inventory), cwd=root, timeout=1800)
        for index, value in enumerate(("3.14.5", "3.15.0rc1", "latest"), 1):
            ev.expect_failure(f"invalid-python-{index}", compose_command("build", "pi",
                              override=f"build.stages.toolchain.python.version={value}"), cwd=root, timeout=300)

        custom_env = resolved_env({"DEV_UID": str(args.custom_uid), "DEV_GID": str(args.custom_gid)})
        ev.run("custom-id-build", compose_command("--progress", "plain", "build", "pi"), cwd=root,
               env=custom_env, timeout=7200)
        ev.run("custom-id-runtime", ["docker", "run", "--rm", "-e", "CHOWN_WORK_ON_START=0",
                                      args.image, "sh", "-c",
                                      f"test $(id -u) = {args.custom_uid}; test $(id -g) = {args.custom_gid}"], cwd=root)
        ev.run("git-diff-check", ["git", "diff", "--check"], cwd=root)
        ev.run(
            "openspec-strict",
            ["docker", "run", "--rm", "-e", "CHOWN_WORK_ON_START=0",
             "-v", f"{root}:/workspace:ro", "-w", "/workspace", args.image,
             "openspec", "validate", "manage-docker-toolchain-versions",
             "--type", "change", "--strict"],
            cwd=root,
            timeout=300,
        )
        ok = True
        return 0
    except EvidenceRunError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        print(f"evidence: {ev.finish(stage_task='6.6', success=ok)}")

if __name__ == "__main__":
    raise SystemExit(main())
