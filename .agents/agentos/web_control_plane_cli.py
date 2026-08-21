"""
Path: .agents/agentos/web_control_plane_cli.py
Purpose: Expose the optional v0.28.1 local Web Control Plane as one opt-in foreground CLI command.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .web_control_plane import serve_web_control_plane


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.28.1 optional Web Control Plane parser."""
    parser = argparse.ArgumentParser(prog="agentos-web-control-plane")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("web-control-plane")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the local Web Control Plane in the foreground."""
    prefix_parser = argparse.ArgumentParser(add_help=False)
    prefix_parser.add_argument("--root", required=True)
    prefix, remaining = prefix_parser.parse_known_args(argv)
    args = build_parser().parse_args(remaining)
    if args.command == "web-control-plane":
        serve_web_control_plane(Path(prefix.root).resolve(), host=args.host, port=args.port)
        return 0
    raise RuntimeError("unknown_web_control_plane_command")


if __name__ == "__main__":
    raise SystemExit(main())
