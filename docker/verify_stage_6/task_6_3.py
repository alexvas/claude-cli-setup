#!/usr/bin/env python3
"""Build and verify a stable Python override image for task 6.3."""
from __future__ import annotations
import argparse
from pathlib import Path
try:
    from .evidence import EvidenceCollector, EvidenceRunError, compose_command, repo_root
except ImportError:
    from evidence import EvidenceCollector, EvidenceRunError, compose_command, repo_root


def main(argv=None) -> int:
    root = repo_root(__file__)
    p = argparse.ArgumentParser()
    p.add_argument("--python-version", default="3.14.6",
                   help="Override version (default: 3.14.6 over experimental 3.14.5)")
    p.add_argument(
        "--inventory", type=Path,
        default=Path("docker/verify_stage_6/inputs/python-3.14.5.toml"),
        help="Source inventory (default: isolated 3.14.5 policy fixture)",
    )
    p.add_argument("--source-image", default="pi-cli-pi:latest")
    p.add_argument("--image", default=None, help="Result tag; defaults to pi-cli-pi:python-VERSION")
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-stage6/6.3"))
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    image = args.image or f"pi-cli-pi:python-{args.python_version}"
    rel_inventory = Path(".docker-generated") / f"python-{args.python_version}.toml"
    override = f"build.stages.toolchain.python.version={args.python_version}"
    ev = EvidenceCollector(args.output_dir, dry_run=args.dry_run)
    ok = False
    try:
        ev.add_file("source_inventory", args.inventory if args.inventory.is_absolute() else root / args.inventory)
        ev.run("override-validate", ["python3", "docker/versions.py", "validate",
                                     "--inventory", str(args.inventory), "--override", override], cwd=root)
        if not args.skip_build:
            previous = ev.run(
                "inspect-previous-default",
                ["docker", "image", "inspect", "--format", "{{.Id}}", args.source_image],
                cwd=root,
                check=False,
            )
            previous_image_id = previous.stdout.strip() if previous.returncode == 0 else ""
            ev.notes["previous_default_image_id"] = previous_image_id or None
            backup_image = "pi-cli-pi:stage6-default-backup"
            if previous_image_id:
                ev.run("tag-default-backup", ["docker", "tag", args.source_image, backup_image], cwd=root)
            try:
                ev.run("override-build", compose_command("--progress", "plain", "build", "pi",
                       inventory=args.inventory, override=override,
                       effective_output=rel_inventory), cwd=root, timeout=7200)
                ev.run("tag-image", ["docker", "tag", args.source_image, image], cwd=root)
            finally:
                if previous_image_id:
                    try:
                        ev.run("restore-default-tag", ["docker", "tag", backup_image, args.source_image], cwd=root)
                    finally:
                        ev.run("remove-default-backup", ["docker", "image", "rm", backup_image],
                               cwd=root, check=False)
        ev.add_file("effective_inventory", root / rel_inventory)
        ev.run("acceptance", ["python3", "docker/verify_versioned_image.py", "--image", image,
                              "--inventory", str(rel_inventory)], cwd=root, timeout=900)
        ev.run("direct-python", ["docker", "run", "--rm", "-e", "CHOWN_WORK_ON_START=0", image,
                                 "bash", "-c", "python --version; python3 --version; readlink -f $(command -v python); readlink -f $(command -v python3)"], cwd=root)
        ok = True
        return 0
    except EvidenceRunError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        print(f"evidence: {ev.finish(stage_task='6.3', success=ok)}")

if __name__ == "__main__":
    raise SystemExit(main())
