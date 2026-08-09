"""
File: .agents/agentos/adaptive_budget_cli.py

Purpose:
    Provide operator CLI access to v0.23.1 model profiles, adaptive-budget history,
    and numeric token calibration observations.

Responsibilities:
    - Inspect local data-only model profiles and their hashes.
    - Inspect persisted adaptive budget decisions and calibration statistics.
    - Record numeric runtime token usage without persisting prompt/response content.
    - Keep calibration mutation outside MCP authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .adaptive_budget import (
    AdaptiveBudgetError,
    budget_history_get,
    model_profiles_get,
    record_token_observation,
    token_calibration_get,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _task_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))


def _require_task(value: str | None) -> str:
    if not value:
        raise AdaptiveBudgetError("task_id_required")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.23.1 adaptive-budget CLI parser."""
    p = argparse.ArgumentParser(prog="agentos adaptive-budget")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("context-model-profiles-list")
    x = sub.add_parser("context-model-profile-get")
    x.add_argument("--model-profile", required=True)

    x = sub.add_parser("context-budget-history")
    _task_arg(x)
    x.add_argument("--limit", type=int, default=20)

    x = sub.add_parser("context-token-calibration-get")
    x.add_argument("--model-profile", required=True)
    x.add_argument("--tokenizer-id", required=True)
    x.add_argument("--limit", type=int, default=32)

    x = sub.add_parser("context-token-observation-record")
    _task_arg(x)
    x.add_argument("--observed-input-tokens", required=True, type=int)
    x.add_argument("--observed-output-tokens", type=int)
    x.add_argument("--revision", type=int)
    x.add_argument("--source", default="runtime_report")
    return p


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.23.1 model-profile/adaptive-budget CLI command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "context-model-profiles-list":
            return _emit(model_profiles_get(root))
        if args.command == "context-model-profile-get":
            return _emit(model_profiles_get(root, args.model_profile))
        if args.command == "context-budget-history":
            return _emit(budget_history_get(root, _require_task(args.task_id), args.limit))
        if args.command == "context-token-calibration-get":
            return _emit(token_calibration_get(root, args.model_profile, args.tokenizer_id, args.limit))
        if args.command == "context-token-observation-record":
            return _emit(
                record_token_observation(
                    root,
                    _require_task(args.task_id),
                    args.observed_input_tokens,
                    args.observed_output_tokens,
                    args.revision,
                    args.source,
                )
            )
    except AdaptiveBudgetError as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
