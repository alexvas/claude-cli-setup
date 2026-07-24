#!/usr/bin/env python3
"""Collect image/tool/inventory introspection evidence for task 6.4."""
from __future__ import annotations
import argparse
from pathlib import Path
try:
    from .evidence import EvidenceCollector, EvidenceRunError, prepare_pi_home, repo_root
except ImportError:
    from evidence import EvidenceCollector, EvidenceRunError, prepare_pi_home, repo_root


def main(argv=None) -> int:
    root = repo_root(__file__)
    p = argparse.ArgumentParser()
    p.add_argument("--image", default="pi-cli-pi:latest")
    p.add_argument("--inventory", type=Path, default=Path(".docker-generated/versions.toml"))
    p.add_argument("--pi-home", type=Path)
    p.add_argument(
        "--skip-extension-install", action="store_true",
        help="Only verify existing extension metadata; do not run the installer",
    )
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-stage6/6.4"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    ev = EvidenceCollector(args.output_dir, dry_run=args.dry_run)
    ok = False
    try:
        owns_pi_home = args.pi_home is None
        pi_home = args.pi_home or (args.output_dir / "pi-home")
        if not args.skip_extension_install:
            pi_home = prepare_pi_home(
                ev, root=root, image=args.image, path=pi_home, reset=owns_pi_home,
            )
        acceptance = ["python3", "docker/verify_versioned_image.py", "--image", args.image,
                      "--inventory", str(args.inventory), "--pi-home", str(pi_home)]
        ev.run("acceptance", acceptance, cwd=root, timeout=900)
        command = """set -eu
node --version
rustc --version
cargo --version
rustfmt --version
cargo clippy --version
uv --version
python --version
python3 --version
ty --version
pi --version
openspec --version
rtk --version
fd --version
git -C /home/dev/.oh-my-zsh rev-parse HEAD
stat -c '%U:%G %a %n' /usr/local/share/pi-cli/versions.toml /usr/local/lib/pi-cli/docker/versions.py
"""
        ev.run("runtime-matrix", ["docker", "run", "--rm", "-e", "CHOWN_WORK_ON_START=0",
                                  args.image, "bash", "-c", command], cwd=root, timeout=900)
        ev.run("image-inventory", ["docker", "run", "--rm", "-e", "CHOWN_WORK_ON_START=0",
                                         args.image, "cat", "/usr/local/share/pi-cli/versions.toml"], cwd=root)
        ev.add_file("host_inventory", root / args.inventory)
        ok = True
        return 0
    except EvidenceRunError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        print(f"evidence: {ev.finish(stage_task='6.4', success=ok)}")

if __name__ == "__main__":
    raise SystemExit(main())
