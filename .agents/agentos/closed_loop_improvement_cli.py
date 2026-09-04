"""
File: .agents/agentos/closed_loop_improvement_cli.py

Purpose:
    Expose v0.31.2 closed-loop readiness and non-authority candidate/proposal creation.

Responsibilities:
    - Inspect closed-loop status.
    - Create a non-active skill candidate from eligible active memory.
    - Inspect policy-improvement readiness from observational skill evaluations.
    - Create/simulate a proposal only when caller explicitly supplies the policy patch.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .closed_loop_improvement import (
    closed_loop_status,
    create_policy_improvement_proposal,
    create_skill_candidate_from_memory,
    policy_improvement_readiness,
)


def _emit(value: Any) -> int:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return (
        0
        if not isinstance(value, dict)
        or value.get("ok", True)
        else 2
    )


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(
            "JSON object required"
        )
    return parsed


def _json_list(value: str) -> list[Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise argparse.ArgumentTypeError(
            "JSON list required"
        )
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.31.2 closed-loop CLI parser."""
    parser = argparse.ArgumentParser(
        prog="agentos closed-loop"
    )
    parser.add_argument("--root")
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("closed-loop-status")

    skill = sub.add_parser(
        "closed-loop-skill-candidate"
    )
    skill.add_argument(
        "--memory-id",
        type=int,
        required=True,
    )

    ready = sub.add_parser(
        "closed-loop-policy-readiness"
    )
    ready.add_argument(
        "--skill-id",
        type=int,
        required=True,
    )

    proposal = sub.add_parser(
        "closed-loop-policy-proposal"
    )
    proposal.add_argument(
        "--skill-id",
        type=int,
        required=True,
    )
    proposal.add_argument(
        "--title",
        required=True,
    )
    proposal.add_argument(
        "--patch-json",
        type=_json_object,
        required=True,
    )
    proposal.add_argument(
        "--expected-benefit",
        required=True,
    )
    proposal.add_argument(
        "--risks-json",
        type=_json_list,
        required=True,
    )
    proposal.add_argument(
        "--rollback-json",
        type=_json_object,
        required=True,
    )
    proposal.add_argument(
        "--created-by",
        required=True,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.31.2 closed-loop command."""
    args = build_parser().parse_args(argv)
    root = Path(
        args.root
        or os.environ.get(
            "AGENTOS_PROJECT_ROOT",
            ".",
        )
    ).resolve()

    try:
        if args.command == "closed-loop-status":
            value = closed_loop_status(root)
        elif (
            args.command
            == "closed-loop-skill-candidate"
        ):
            value = create_skill_candidate_from_memory(
                root,
                args.memory_id,
            )
        elif (
            args.command
            == "closed-loop-policy-readiness"
        ):
            value = policy_improvement_readiness(
                root,
                args.skill_id,
            )
        elif (
            args.command
            == "closed-loop-policy-proposal"
        ):
            value = create_policy_improvement_proposal(
                root,
                skill_id=args.skill_id,
                title=args.title,
                policy_patch=args.patch_json,
                expected_benefit=(
                    args.expected_benefit
                ),
                risks=[
                    str(item)
                    for item
                    in args.risks_json
                ],
                rollback_plan=(
                    args.rollback_json
                ),
                created_by=args.created_by,
            )
        else:
            raise RuntimeError(
                "unknown_closed_loop_command"
            )
        return _emit(value)
    except Exception as exc:
        return _emit(
            {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }
        )


if __name__ == "__main__":
    raise SystemExit(main())
