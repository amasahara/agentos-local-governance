"""
File: .agents/agentos/models.py

Purpose:
    Define shared AgentOS data contracts.

Responsibilities:
    - Represent requirement clarity results.
    - Represent documentation findings.
"""
from dataclasses import dataclass
@dataclass
class ClarityAssessment:
    """Represent semantic completeness of a user request.

    Args:
        intent: Normalized task intent.
        target: Affected feature, module, file, or behavior.
        expected_behavior: Desired result.
        current_behavior: Existing behavior or problem.
        acceptance_criteria: Verifiable completion conditions.
        scope: Approved modification boundary.
        risk: Low, medium, or high risk.
        ambiguities: Missing details that can change implementation.
        assumptions: Explicit reversible assumptions.
        status: Ready or needs clarification.
    """
    intent:str|None; target:str|None; expected_behavior:str|None; current_behavior:str|None; acceptance_criteria:list[str]; scope:str|None; risk:str; ambiguities:list[str]; assumptions:list[str]; status:str
@dataclass
class DocumentationFinding:
    """Represent one source-documentation violation.

    Args:
        path: Project-relative source path.
        symbol: Qualified symbol name or None for file findings.
        line_start: Relevant source line.
        severity: Error, warning, or needs_review.
        code: Stable finding code.
        message: Human-readable explanation.
    """
    path:str; symbol:str|None; line_start:int|None; severity:str; code:str; message:str
