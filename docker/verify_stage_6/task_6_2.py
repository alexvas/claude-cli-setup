#!/usr/bin/env python3
"""Build and verify the default image for OpenSpec task 6.2."""
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
    p.add_argument("--image", default="pi-cli-pi:latest")
    p.add_argument("--inventory", type=Path, default=Path(".docker-generated/docker-constructor.toml"))
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-stage6/6.2"))
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    ev = EvidenceCollector(args.output_dir, dry_run=args.dry_run)
    ok = False
    try:
        ev.run("versions-validate", ["python3", "docker/versions.py", "validate"], cwd=root)
        if not args.skip_build:
            ev.run("default-build", compose_command("--progress", "plain", "build", "pi"), cwd=root, timeout=7200)
        ev.add_file("effective_inventory", root / args.inventory)
        ev.run("verify-runtime", ["sh", "docker/verify-runtime.sh", args.image], cwd=root, timeout=900)
        ev.run("acceptance", ["python3", "docker/verify_versioned_image.py", "--image", args.image,
                              "--inventory", str(args.inventory)], cwd=root, timeout=900)
        ev.run("image-inspect", ["docker", "image", "inspect", args.image], cwd=root)
        ev.run("image-history", ["docker", "history", "--no-trunc", args.image], cwd=root)
        ok = True
        return 0
    except EvidenceRunError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        print(f"evidence: {ev.finish(stage_task='6.2', success=ok)}")

if __name__ == "__main__":
    raise SystemExit(main())
