"""
Path: .agents/agentos/command_center_cli.py
Purpose: Expose the v0.28.0 Architecture & Agent Command Center through read-only CLI commands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .command_center import (
    command_center_human_actions,
    command_center_section,
    command_center_snapshot,
    render_command_center,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-center extension parser."""
    parser = argparse.ArgumentParser(prog="agentos-command-center")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("command-center")
    p.add_argument("--format", choices=("text", "json"), default="text")

    sub.add_parser("command-center-snapshot")
    sub.add_parser("command-center-actions")

    p = sub.add_parser("command-center-section")
    p.add_argument(
        "--section",
        required=True,
        choices=("architecture", "execution", "compliance", "human_actions", "authority"),
    )
    return parser


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    """Execute one read-only command-center CLI command."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--root", required=True)
    prefix, remaining = parser.parse_known_args(argv)
    args = build_parser().parse_args(remaining)
    root = Path(prefix.root).resolve()

    if args.command == "command-center":
        snapshot = command_center_snapshot(root)
        if args.format == "json":
            _emit(snapshot)
        else:
            print(render_command_center(snapshot), end="")
        return 0
    if args.command == "command-center-snapshot":
        _emit(command_center_snapshot(root))
        return 0
    if args.command == "command-center-actions":
        _emit(command_center_human_actions(root))
        return 0
    if args.command == "command-center-section":
        _emit(command_center_section(root, args.section))
        return 0
    raise RuntimeError("unknown_command_center_command")


if __name__ == "__main__":
    raise SystemExit(main())
