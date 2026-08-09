# AgentOS v0.22.7 Developer Guide

Current version: **0.22.7**, schema **43**.

Required erasure flow: `request-create → plan-create → plan-review → plan-approve → execute`. Request and plan records are immutable; review, approval, and execution are separate records. Use the canonical `entity_uuid`, not a raw subject identifier. Resolve any related active/in-doubt operation before execution. After execution, inspect `local_erasure_completed`; when `external_target_erasure_required` is true, route the external request to the TARGET authority outside AgentOS.

MCP is inspection-only for this lifecycle.
