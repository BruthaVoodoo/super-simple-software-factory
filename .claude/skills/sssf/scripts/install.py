#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""/install — stamp the SSSF factory from the skill into the cwd. Idempotent.

Usage:
    uv run <skill>/scripts/install.py [--force]

This is the direct installer. It delegates to the shared installation logic in
`sssf_cli.installer` — the exact same code `sssf init` uses — and keeps its
own CLI surface and output. It does NOT write a manifest; that is `sssf init`'s
behavior, so legacy installs stay byte-identical to what they always produced.
"""
import argparse
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# sssf_cli lives at the factory root: skill/../../ = skills/sssf/../../ = the
# skill root's parent's parent — i.e. the factory checkout root.
FACTORY_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args()

    root = Path.cwd()
    sys.path.insert(0, str(FACTORY_ROOT))
    from sssf_cli.installer import TEMPLATES as SHARED_TEMPLATES, apply

    assert SHARED_TEMPLATES == TEMPLATES, (
        f"installer template mismatch: {SHARED_TEMPLATES} != {TEMPLATES}")

    plan = apply(root, force=args.force, write_manifest=False)
    print(f"sssf installed into {root}")
    print(f"  stamped: {len(plan.stamped)} file(s)")
    for s in plan.stamped:
        print(f"    + {s}")
    if plan.skipped:
        print(f"  skipped (already exist, use --force to overwrite): {len(plan.skipped)}")
    if plan.gitignore_added:
        for g in plan.gitignore_added:
            print(f"    + {g}")
    print("\nnext steps:")
    print("  1. cp .env.sample .env   # then set the key(s) your roster needs")
    print("  2. just demo             # two cheap read-only runs, end to end")
    print("  3. just sessions         # what just happened")
    print("  4. just obs              # the trace UI, needs bun")
    print("\n  no just? the raw form of step 2 is:")
    print("     uv run adws/adw_prompt.py \"say hello\" --agent scout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
