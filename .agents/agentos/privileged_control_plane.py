"""
File: .agents/agentos/privileged_control_plane.py

Purpose:
    Explicit human/operator privileged control-plane entrypoint.

Boundary:
    - Only CONTROL_PLANE_COMMANDS may dispatch here.
    - Normal agent-plane commands are rejected.
    - Existing governed mutation enforcement remains authoritative.
    - Hard anti-bypass/exclusivity is deferred to v0.28.4.
"""
from __future__ import annotations

from .cli_runtime import main as runtime_main


def main(argv: list[str] | None = None) -> int:
    return runtime_main(argv, plane="control")


if __name__ == "__main__":
    raise SystemExit(main())
