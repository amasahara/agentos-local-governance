"""
File: .agents/agentos/cli_identity.py

Purpose:
    Resolve the visible CLI program identity from the active
    AgentOS execution plane.

The structural control-plane boundary is enforced by cli_runtime.
This helper only keeps argparse/help identity consistent.
"""
from __future__ import annotations

import os


def cli_program() -> str:
    """Return the launcher identity for the active execution plane."""
    return (
        "agentos-admin"
        if os.environ.get("AGENTOS_EXECUTION_PLANE") == "control"
        else "agentos"
    )
