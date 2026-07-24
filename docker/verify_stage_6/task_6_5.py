#!/usr/bin/env python3
"""Collect BuildKit cache invalidation evidence for task 6.5.

Pass independently prepared, valid inventories as --case SCOPE=PATH.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
try:
    from .evidence import EvidenceCollector, EvidenceRunError, compose_command, repo_root
except ImportError:
    from evidence import EvidenceCollector, EvidenceRunError, compose_command, repo_root


def _case(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected SCOPE=INVENTORY_PATH")
    scope, path = value.split("=", 1)
    if not scope or not path:
        raise argparse.ArgumentTypeError("expected non-empty SCOPE=INVENTORY_PATH")
    return scope, Path(path)


def main(argv=None) -> int:
    root = repo_root(__file__)
    p = argparse.ArgumentParser()
    p.add_argument("--case", action="append", type=_case, default=[], metavar="SCOPE=PATH")
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/pi-stage6/6.5"))
    p.add_argument("--skip-baseline", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if not args.case:
        args.case = [
            ("toolchain-python", Path("docker/verify_stage_6/inputs/python-3.14.5.toml")),
            ("rust-profile", Path("docker/verify_stage_6/inputs/cache-rust-profile.toml")),
            ("runtime-extensions", Path("docker/verify_stage_6/inputs/cache-runtime-extensions.toml")),
        ]
    ev = EvidenceCollector(args.output_dir, dry_run=args.dry_run)
    ok = False
    try:
        if not args.skip_baseline:
            ev.run("baseline-build", compose_command("--progress", "plain", "build", "pi"), cwd=root, timeout=7200)
            repeat = ev.run("repeat-build", compose_command("--progress", "plain", "build", "pi"), cwd=root, timeout=7200)
            repeat_output = repeat.stdout + "\n" + repeat.stderr
            ev.notes["repeat_cached_markers"] = len(re.findall(r"\bCACHED\b", repeat_output))
        case_summaries = {}
        for index, (scope, inventory) in enumerate(args.case, 1):
            resolved = inventory if inventory.is_absolute() else root / inventory
            ev.add_file(f"case_{scope}_inventory", resolved)
            if index > 1:
                ev.run(
                    f"baseline-before-{index}-{scope}",
                    compose_command("--progress", "plain", "build", "pi"),
                    cwd=root,
                    timeout=7200,
                )
            proc = ev.run(f"case-{index}-{scope}", compose_command("--progress", "plain", "build", "pi",
                          inventory=resolved), cwd=root, timeout=7200)
            build_output = proc.stdout + "\n" + proc.stderr
            case_summaries[scope] = {
                "cached_markers": len(re.findall(r"\bCACHED\b", build_output)),
                "built_markers": len(re.findall(r"\bDONE\b", build_output)),
            }
        ev.notes["cache_cases"] = case_summaries
        ok = True
        return 0
    except EvidenceRunError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        print(f"evidence: {ev.finish(stage_task='6.5', success=ok)}")

if __name__ == "__main__":
    raise SystemExit(main())
