"""
File: .agents/agentos/mcp_catalog.py

Purpose:
    Backward-compatible facade for the active MCP feature runtime.

The catalog no longer imports historical compatibility gateway modules. New code should
import mcp_feature_runtime directly; historical callers may continue importing
FEATURE_TOOLS, FEATURE_HANDLERS, REGISTRATIONS, and build_feature_catalog here.
"""
from __future__ import annotations

from .mcp_feature_runtime import (
    FEATURE_HANDLERS,
    FEATURE_TOOLS,
    REGISTRATIONS,
    FeatureHandler,
    build_feature_catalog,
)

__all__ = [
    "FEATURE_HANDLERS",
    "FEATURE_TOOLS",
    "REGISTRATIONS",
    "FeatureHandler",
    "build_feature_catalog",
]
