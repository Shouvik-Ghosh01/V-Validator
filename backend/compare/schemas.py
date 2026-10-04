from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any


# -----------------------------
# COMPARISON MODE
# -----------------------------
class ComparisonMode(str, Enum):
    """
    Which semantic relationship the two uploaded PDFs have.

    TEMPLATE_VS_OUTPUT  PDF A is a client/template script, PDF B is an executed
                        output report            (EXPECTED vs ACTUAL)
    OUTPUT_VS_OUTPUT    both PDFs are executed output reports   (RUN A vs RUN B)
    """

    TEMPLATE_VS_OUTPUT = "template_vs_output"
    OUTPUT_VS_OUTPUT = "output_vs_output"


# Peer-comparison difference vocabulary (Output-vs-Output only).
# Deliberately neutral: nothing here implies expected/actual or pass/fail.
DIFF_CHANGED = "changed"
DIFF_MISSING = "missing"        # present in Output A, absent from Output B
DIFF_ADDITIONAL = "additional"  # absent from Output A, present in Output B
DIFF_IDENTICAL = "identical"
DIFF_AMBIGUOUS = "ambiguous"    # cannot be confirmed to be the same logical item


# -----------------------------
# SETUP STEP (shared)
# -----------------------------
@dataclass
class SetupStep:
    step_number: int
    procedure: str


# -----------------------------
# CLIENT PDF EXECUTION STEP
# -----------------------------
@dataclass
class ClientExecutionStep:
    step_number: int
    procedure: str
    expected_results: str


# -----------------------------
# EXECUTED PDF EXECUTION STEP
# -----------------------------
@dataclass
class ExecutedExecutionStep:
    step_number: int
    procedure: str
    expected_results: str
    actual_results: str
    pass_fail: str


# -----------------------------
# CLIENT SCRIPT
# -----------------------------
@dataclass
class ClientScript:
    setup_steps: List[SetupStep]
    execution_steps: List[ClientExecutionStep]
    metadata: Dict[str, Any] = field(default_factory=dict)


# -----------------------------
# EXECUTED SCRIPT
# -----------------------------
@dataclass
class ExecutedScript:
    pre_test_setup: List[SetupStep]
    execution_steps: List[ExecutedExecutionStep]
    metadata: Dict[str, Any] = field(default_factory=dict)