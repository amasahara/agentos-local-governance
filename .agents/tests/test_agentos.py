"""
File: .agents/tests/test_agentos.py

Purpose:
    Validate compatibility and v0.7 governance behavior.

Responsibilities:
    - Test clarification and approval gates.
    - Test tool governance, cache, index, and documentation contracts.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.agents'))
from agentos.core import *
from agentos.tooling import guard_tool, record_tool_execution
from agentos.cache import cache_store, cache_lookup
from agentos.indexing import index_build, index_query
from agentos.documentation import documentation_scan


def project(tmp_path: Path) -> Path:
    """Create an isolated AgentOS project.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Initialized project root.
    """
    (tmp_path / 'AGENTS.md').write_text('# test', encoding='utf-8')
    (tmp_path / '.agents/config').mkdir(parents=True)
    cfg = json.loads((ROOT / '.agents/config/governance.json').read_text(encoding='utf-8'))
    (tmp_path / '.agents/config/governance.json').write_text(json.dumps(cfg), encoding='utf-8')
    return tmp_path


def ready(root: Path) -> None:
    """Create and approve a ready task.

    Args:
        root: Isolated project root.

    Returns:
        None.
    """
    x = assess_clarity({
        'intent': 'modify_existing_feature', 'target': 'src/a.py',
        'expected_behavior': 'Return 2', 'current_behavior': 'Return 1',
        'acceptance_criteria': ['Returns 2'], 'scope': 'src/a.py', 'risk': 'low'
    })
    save_task(root, 'T1', 'change', x)
    approve_task(root, 'T1')


def test_ambiguous():
    x = assess_clarity({'intent': 'modify_existing_feature'})
    assert x.status == 'needs_clarification'
    assert suggested_questions(x)


def test_ready_write(tmp_path):
    root = project(tmp_path)
    ready(root)
    assert check_write(root, 'T1', 'src/a.py')['allowed']


def test_unknown_tool(tmp_path):
    root = project(tmp_path)
    ready(root)
    assert guard_tool(root, 'T1', 'mystery', {})['reason'] == 'unclassified_tool_fail_closed'


def test_network_local_first(tmp_path):
    root = project(tmp_path)
    ready(root)
    justification = {'reason_code': 'official_documentation_required', 'detail': 'Need official docs.'}
    assert guard_tool(root, 'T1', 'web_search', {'q': 'x'}, justification)['reason'] == 'network_call_requires_local_attempt'
    record_tool_execution(root, 'T1', 'bounded_file_read', {'path': 'x'}, True, 'local')
    assert guard_tool(root, 'T1', 'web_search', {'q': 'x'}, justification)['allowed']


def test_cache(tmp_path):
    root = project(tmp_path)
    path = root / 'src/x.py'
    path.parent.mkdir(parents=True)
    path.write_text('x=1\n', encoding='utf-8')
    cache_store(root, 'T1', 'src/x.py', 'one', 1, 5)
    assert cache_lookup(root, 'T1', 'src/x.py', 1, 5)['status'] == 'hit'
    path.write_text('x=200\n', encoding='utf-8')
    assert cache_lookup(root, 'T1', 'src/x.py', 1, 5)['status'] == 'miss'


def test_index_qualname(tmp_path):
    root = project(tmp_path)
    path = root / 'src/x.py'
    path.parent.mkdir(parents=True)
    path.write_text(
        'class A:\n'
        '    def save(self):\n'
        '        return 1\n\n'
        'class B:\n'
        '    def save(self):\n'
        '        return 2\n',
        encoding='utf-8',
    )
    first = index_build(root)
    second = index_build(root)
    names = {x['qualname'] for x in index_query(root, 'save')}
    assert first['updated_files'] == 1
    assert second['skipped_files'] == 1
    assert {'A.save', 'B.save'} <= names


def test_docs_missing_io(tmp_path):
    root = project(tmp_path)
    path = root / 'src/x.py'
    path.parent.mkdir(parents=True)
    source = '''"""
File: src/x.py

Purpose:
    Demo module.

Responsibilities:
    - Demonstrate checks.
"""

def add(a: int, b: int) -> int:
    """Add two values."""
    return a + b
'''
    path.write_text(source, encoding='utf-8')
    codes = {x['code'] for x in documentation_scan(root)['findings']}
    assert 'missing_input_documentation' in codes
    assert 'missing_output_documentation' in codes


def test_docs_complete(tmp_path):
    root = project(tmp_path)
    path = root / 'src/x.py'
    path.parent.mkdir(parents=True)
    source = '''"""
File: src/x.py

Purpose:
    Provide arithmetic operations.

Responsibilities:
    - Add validated integers.
"""

def add(a: int, b: int) -> int:
    """Add two integer values.

    Args:
        a: First integer.
        b: Second integer.

    Returns:
        Sum of both integers.
    """
    return a + b
'''
    path.write_text(source, encoding='utf-8')
    assert documentation_scan(root)['status'] == 'passed'


def test_release_sync():
    assert instruction_check(ROOT)['ok']
    assert docs_check(ROOT)['ok']
