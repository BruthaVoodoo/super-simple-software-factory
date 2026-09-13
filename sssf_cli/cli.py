"""sssf CLI — argument parsing and command dispatch.

Subcommands land task-by-task; anything not implemented yet exits 2 with a
clear message rather than pretending to work.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__

COMMANDS = ("init", "update", "doctor", "install-skill")


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"sssf {args.command}: not implemented until a later task",
          file=sys.stderr)
    return 2


def _init(args: argparse.Namespace) -> int:
    from .installer import apply, plan as make_plan, print_plan
    target = Path.cwd()
    if args.dry_run:
        plan = make_plan(target, force=args.force)
        print(f"sssf plan for {target} (dry run — nothing was written)")
        print(f"  would stamp: {len(plan.stamped)} file(s)")
        for relative in plan.stamped:
            print(f"    + {relative}")
        print(f"  would skip (already exist): {len(plan.skipped)}")
        for relative in plan.skipped:
            print(f"    = {relative}")
        for entry in plan.gitignore_added:
            print(f"  would append to .gitignore: {entry}")
        return 0
    plan = apply(target, force=args.force, write_manifest=True)
    print_plan(plan, target=target)
    print("\nnext steps:")
    print("  1. cp .env.sample .env   # then set the key(s) your roster needs")
    print("  2. just demo             # two cheap read-only runs, end to end")
    print("  3. sssf doctor           # verify the environment")
    return 0


def _update(args: argparse.Namespace) -> int:
    from .installer import apply_update, plan_update, print_update
    target = Path.cwd()
    if args.dry_run:
        plan = plan_update(target)
        print(f"sssf update plan for {target} (dry run — nothing was written)")
        print_update(plan)
        return 3 if plan.conflicts else 0
    plan = apply_update(target, force=args.force)
    print(f"sssf updated {target}")
    print_update(plan)
    if plan.conflicts and not args.force:
        print("\nuser-modified files were NOT overwritten — pass --force to overwrite")
        return 3
    return 0


def _install_skill(args: argparse.Namespace) -> int:
    from .skill import install
    target = Path(args.target) if args.target else Path.cwd()
    plan = install(target, force=args.force)
    print(f"sssf skill installed into {target / '.claude' / 'skills' / 'sssf'}")
    print(f"  stamped: {len(plan.stamped)} file(s)")
    if plan.skipped:
        print(f"  skipped (already exist, use --force to overwrite): "
              f"{len(plan.skipped)}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import run_checks
    checks = run_checks(Path.cwd(), config=args.config)
    for check in checks:
        mark = "PASS" if check.ok else "FAIL"
        print(f"  [{mark}] {check.name}: {check.detail}")
    print("  [info] credentials: not checked — validity is proven only by a "
          "real run (just smoke-real-pi)")
    failed = [check for check in checks if not check.ok]
    print(f"sssf doctor: {'OK' if not failed else f'{len(failed)} check(s) failed'}")
    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sssf",
        description="Install, update, and verify the SSSF factory — no Claude "
                    "Code required.")
    parser.add_argument("--version", action="version",
                        version=f"sssf {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    init_parser = sub.add_parser("init", help="stamp the factory into the current directory")
    init_parser.add_argument("--force", action="store_true",
                             help="overwrite existing files")
    init_parser.add_argument("--dry-run", action="store_true",
                             help="report what would change; write nothing")
    update_parser = sub.add_parser("update", help="apply new factory versions; protect user edits")
    update_parser.add_argument("--force", action="store_true",
                               help="overwrite user-modified files too")
    update_parser.add_argument("--dry-run", action="store_true",
                               help="classify without writing")
    doctor_parser = sub.add_parser("doctor", help="verify the environment (credential-free)")
    doctor_parser.add_argument("--config", default=None,
                               help="roster config path (target-relative)")
    skill = sub.add_parser("install-skill",
                           help="copy the optional /sssf operator frontend skill")
    skill.add_argument("--target", default=None,
                       help="installation root (default: the current directory)")
    skill.add_argument("--force", action="store_true",
                       help="overwrite an existing skill copy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dispatch = {"init": _init, "update": _update, "doctor": _doctor,
                "install-skill": _install_skill}
    handler = dispatch.get(args.command)
    if handler is None:
        print(f"sssf {args.command}: not implemented until a later task",
              file=sys.stderr)
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
