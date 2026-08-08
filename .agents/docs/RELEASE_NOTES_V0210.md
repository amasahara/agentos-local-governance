# AgentOS v0.21.0 Release Notes

v0.21.0 adds the Source/Target Database Boundary and advances AgentOS SQLite schema from 34 to 35.

Key guarantees:

- exactly one TARGET per database consolidation;
- verified SOURCE connections are catalog/SELECT-only;
- source write operations are denied fail-closed;
- target writes remain disabled until v0.22.0;
- raw credentials/DSNs are never stored;
- domain match is required between SOURCE and TARGET;
- MCP exposure is read-only and contains no arbitrary SQL execution.
