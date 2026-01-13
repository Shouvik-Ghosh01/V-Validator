from dataclasses import dataclass
from typing import List


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


# -----------------------------
# EXECUTED SCRIPT
# -----------------------------
@dataclass
class ExecutedScript:
    pre_test_setup: List[SetupStep]
    execution_steps: List[ExecutedExecutionStep]
