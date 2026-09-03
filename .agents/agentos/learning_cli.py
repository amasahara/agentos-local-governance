"""
File: .agents/agentos/learning_cli.py

Purpose:
    Expose privacy-safe read-only governed-learning inspection commands.

Responsibilities:
    - Register learning status, signal, link, and knowledge-usage read commands.
    - Keep learning mutation, promotion, approval, and activation out of the agent CLI.
    - Emit deterministic JSON suitable for local operators and release validation.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any
from .learning_signals import LearningSignalError, knowledge_usage_get, learning_signal_links_get, learning_signals_get, learning_status

def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2

def build_parser() -> argparse.ArgumentParser:
    """Build the read-only governed-learning CLI parser."""
    p=argparse.ArgumentParser(prog="agentos learning"); p.add_argument("--root",required=True)
    s=p.add_subparsers(dest="command",required=True); s.add_parser("learning-status")
    x=s.add_parser("learning-signals-show"); x.add_argument("--task-id"); x.add_argument("--signature-hash"); x.add_argument("--limit",type=int,default=100)
    x=s.add_parser("learning-signal-links-show"); x.add_argument("--signal-id"); x.add_argument("--limit",type=int,default=100)
    x=s.add_parser("knowledge-usage-show"); x.add_argument("--task-id"); x.add_argument("--knowledge-kind",choices=["skill","memory","finding"]); x.add_argument("--limit",type=int,default=100)
    return p

def main(argv: list[str] | None=None) -> int:
    """Execute one read-only governed-learning CLI command."""
    a=build_parser().parse_args(argv); root=Path(a.root).resolve()
    try:
        if a.command=="learning-status": return _emit(learning_status(root))
        if a.command=="learning-signals-show": return _emit(learning_signals_get(root,task_id=a.task_id,signature_hash=a.signature_hash,limit=a.limit))
        if a.command=="learning-signal-links-show": return _emit(learning_signal_links_get(root,signal_id=a.signal_id,limit=a.limit))
        if a.command=="knowledge-usage-show": return _emit(knowledge_usage_get(root,task_id=a.task_id,knowledge_kind=a.knowledge_kind,limit=a.limit))
    except LearningSignalError as exc: return _emit({"ok":False,"error":str(exc)})
    return 2
if __name__=="__main__": raise SystemExit(main())
