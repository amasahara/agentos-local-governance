from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import (
    project_root, assess_clarity, suggested_questions, save_task, approve_task,
    instruction_check, detect_environment, enforce_tool_budget, record_tool_call,
    resolve_placement, duplicate_scan, similar_symbols, check_write,
    prepare_change, runtime_path, docs_check
)


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(prog="agentos")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("clarity-check")
    s.add_argument("--task-id", required=True)
    s.add_argument("--request", required=True)
    s.add_argument("--payload", required=True, help="JSON object")

    s = sub.add_parser("approve-task")
    s.add_argument("task_id")

    sub.add_parser("instruction-check")
    sub.add_parser("docs-check")

    s = sub.add_parser("detect-environment")
    s.add_argument("--session-id", required=True)

    s = sub.add_parser("tool-guard")
    s.add_argument("--task-id", required=True)
    s.add_argument("--tool", required=True)
    s.add_argument("--args", required=True)

    s = sub.add_parser("record-tool")
    s.add_argument("--task-id", required=True)
    s.add_argument("--tool", required=True)
    s.add_argument("--args", required=True)
    s.add_argument("--success", action="store_true")
    s.add_argument("--error")
    s.add_argument("--summary", default="")

    s = sub.add_parser("resolve-placement")
    s.add_argument("filename")
    s.add_argument("--feature")
    s.add_argument("--layer")
    s.add_argument("--temporary", action="store_true")
    s.add_argument("--task-id")

    s = sub.add_parser("duplicate-scan")
    s.add_argument("scope", nargs="?", default="src")

    s = sub.add_parser("similar-symbols")
    s.add_argument("query")

    s = sub.add_parser("check-write")
    s.add_argument("path")
    s.add_argument("--task-id", required=True)

    s = sub.add_parser("prepare-change")
    s.add_argument("--task-id", required=True)
    s.add_argument("--operation", choices=["create", "modify", "delete"], required=True)
    s.add_argument("--target", required=True)
    s.add_argument("--intent", required=True)
    s.add_argument("--symbols", default="[]")
    s.add_argument("--feature")
    s.add_argument("--layer")

    s = sub.add_parser("runtime-path")
    s.add_argument("task_id")
    s.add_argument("kind")
    s.add_argument("filename")

    args = p.parse_args()
    root = project_root()

    if args.cmd == "clarity-check":
        payload = json.loads(args.payload)
        a = assess_clarity(payload)
        save_task(root, args.task_id, args.request, a)
        out = a.__dict__.copy()
        out["clarification_questions"] = suggested_questions(a) if a.status != "ready" else []
        emit(out)
    elif args.cmd == "approve-task":
        approve_task(root, args.task_id)
        emit({"approved": True, "task_id": args.task_id})
    elif args.cmd == "instruction-check":
        emit(instruction_check(root))
    elif args.cmd == "docs-check":
        emit(docs_check(root))
    elif args.cmd == "detect-environment":
        emit(detect_environment(root, args.session_id))
    elif args.cmd == "tool-guard":
        emit(enforce_tool_budget(root, args.task_id, args.tool, json.loads(args.args)))
    elif args.cmd == "record-tool":
        emit(record_tool_call(root, args.task_id, args.tool, json.loads(args.args),
                              args.success, args.error, args.summary))
    elif args.cmd == "resolve-placement":
        emit({"path": resolve_placement(root, args.filename, args.feature, args.layer,
                                         args.temporary, args.task_id)})
    elif args.cmd == "duplicate-scan":
        emit(duplicate_scan(root, args.scope))
    elif args.cmd == "similar-symbols":
        emit(similar_symbols(root, args.query))
    elif args.cmd == "check-write":
        emit(check_write(root, args.task_id, args.path))
    elif args.cmd == "prepare-change":
        emit(prepare_change(root, args.task_id, args.operation, args.target, args.intent,
                            json.loads(args.symbols), args.feature, args.layer))
    elif args.cmd == "runtime-path":
        emit({"path": runtime_path(root, args.task_id, args.kind, args.filename)})


if __name__ == "__main__":
    main()
