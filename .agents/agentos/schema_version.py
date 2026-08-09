"""
File: .agents/agentos/schema_version.py

Purpose:
    Publish the single authoritative AgentOS SQLite schema version.

Responsibilities:
    - Provide one dependency-light schema version constant.
    - Prevent feature modules from carrying divergent schema-version numbers.
"""

CURRENT_SCHEMA_VERSION = 44
