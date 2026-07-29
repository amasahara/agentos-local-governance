"""
File: .agents/agentos/policy.py

Purpose:
    Load and validate machine-readable AgentOS policy.

Responsibilities:
    - Parse governance JSON.
    - Validate required sections and enum values.
    - Fail closed when policy is malformed.
"""
import json
from pathlib import Path
from typing import Any

def load(root:Path)->dict[str,Any]:
    """Load validated governance configuration.

    Args:
        root: Absolute AgentOS project root.

    Returns:
        Parsed governance dictionary.

    Raises:
        RuntimeError: Required configuration is missing or invalid.
    """
    p=root/'.agents/config/governance.json'
    if not p.is_file(): raise RuntimeError('Missing governance.json')
    data=json.loads(p.read_text(encoding='utf-8')); validate(data); return data

def validate(data:dict[str,Any])->None:
    """Validate required policy sections.

    Args:
        data: Parsed governance dictionary.

    Returns:
        None.

    Raises:
        RuntimeError: A required section or supported value is missing.
    """
    for k in ('version','tool_execution_policy','tool_policy','code_documentation_policy'):
        if k not in data: raise RuntimeError(f'Missing governance key: {k}')
    if data['tool_policy'].get('mode') not in {'audit','warn','enforce'}: raise RuntimeError('Unsupported tool policy mode')
