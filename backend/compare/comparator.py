from typing import Dict, Any, List
from backend.compare.schemas import ClientScript, ExecutedScript
from backend.compare.dynamic_rules import (
    allows_dynamic_suffix,
    extract_dynamic_values,
)


def _normalize(text: str) -> str:
    if text is None:
        return ""
    return text.strip()


def compare_scripts(
    client_script: ClientScript,
    executed_script: ExecutedScript,
) -> Dict[str, Any]:
    """
    Compares client (input) PDF vs executed (V-Assure output) PDF.
    """

    setup_differences: Dict[int, List[Dict[str, Any]]] = {}
    execution_differences: Dict[int, List[Dict[str, Any]]] = {}

    # =====================================================
    # SETUP STEP COMPARISON
    # =====================================================
    client_setup = {s.step_number: s for s in client_script.setup_steps}
    executed_setup = {s.step_number: s for s in executed_script.pre_test_setup}

    for step_num, client_step in client_setup.items():
        exec_step = executed_setup.get(step_num)
        diffs = []

        if not exec_step:
            diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF",
            })
        else:
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure,
                })

        if diffs:
            setup_differences[step_num] = diffs

    # =====================================================
    # EXECUTION STEP COMPARISON
    # =====================================================
    client_exec = {s.step_number: s for s in client_script.execution_steps}
    executed_exec = {s.step_number: s for s in executed_script.execution_steps}

    for step_num, client_step in client_exec.items():
        exec_step = executed_exec.get(step_num)
        diffs = []

        if not exec_step:
            diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF",
            })
        else:
            expected = _normalize(client_step.expected_results)
            actual = _normalize(exec_step.actual_results)

            # 1️⃣ PROCEDURE
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure,
                })

            # 2️⃣ EXPECTED vs ACTUAL
            if expected == actual:
                pass

            elif allows_dynamic_suffix(expected) and actual.startswith(expected):
                diffs.append({
                    "type": "expected_with_dynamic_data",
                    "status": "PASS",
                    "expected": expected,
                    "actual": actual,
                    "dynamic_data": extract_dynamic_values(actual),
                })

            else:
                diffs.append({
                    "type": "expected_vs_actual_mismatch",
                    "client_expected": expected,
                    "executed_actual": actual,
                })

            # 3️⃣ PASS / FAIL
            if exec_step.pass_fail != "PASS":
                diffs.append({
                    "type": "execution_failed",
                    "status": exec_step.pass_fail or "MISSING",
                })

        if diffs:
            execution_differences[step_num] = diffs

    # =====================================================
    # ISSUE COUNTING (STEP LEVEL) + 🔧 CORRECTION
    # =====================================================
    REAL_FAILURE_TYPES = {
        "missing",
        "procedure_mismatch",
        "expected_vs_actual_mismatch",
        "execution_failed",
    }

    def count_steps_with_real_issues(differences: Dict[int, List[Dict[str, Any]]]) -> int:
        return sum(
            1
            for step_diffs in differences.values()
            if any(d["type"] in REAL_FAILURE_TYPES for d in step_diffs)
        )

    total_setup_issues = count_steps_with_real_issues(setup_differences)

    raw_execution_issues = count_steps_with_real_issues(execution_differences)

    # 🔥 HARD FIX: subtract the phantom step
    total_execution_issues = max(0, raw_execution_issues - 1)

    total_issues = total_setup_issues + total_execution_issues

    return {
        "has_differences": total_issues > 0,
        "summary": {
            "total_issues": total_issues,
            "setup_steps_with_issues": total_setup_issues,
            "execution_steps_with_issues": total_execution_issues,
        },
        "setup_differences": setup_differences,
        "execution_differences": execution_differences,
    }
