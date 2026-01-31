from typing import Dict, Any, List
import logging

from backend.compare.schemas import ClientScript, ExecutedScript
from backend.compare.dynamic_rules import (
    allows_dynamic_suffix,
    extract_dynamic_values,
)

# ------------------------------------------------------------------
# Logger setup
# ------------------------------------------------------------------
logger = logging.getLogger("pdf_comparator")
logger.setLevel(logging.INFO)

# If not already configured elsewhere
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(levelname)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _normalize(text: str) -> str:
    """Normalize text for safe comparison."""
    return (text or "").strip()


# ------------------------------------------------------------------
# Main comparator
# ------------------------------------------------------------------
def compare_scripts(
    client_script: ClientScript,
    executed_script: ExecutedScript,
) -> Dict[str, Any]:
    """
    Compares client (input) PDF vs executed (V-Assure output) PDF.

    EXECUTION RULES:
    1. Procedure must match exactly
    2. Expected results must match exactly OR
       Expected must be a PREFIX of Actual when dynamic data is allowed
    3. PASS/FAIL:
        - PASS  -> OK
        - FAIL  -> ISSUE
        - MISSING / None -> IGNORE (NOT an issue)
    """

    setup_differences: Dict[int, List[Dict[str, Any]]] = {}
    execution_differences: Dict[int, List[Dict[str, Any]]] = {}

    logger.info("Starting PDF comparison")
    logger.info(
        "Client steps: setup=%d, execution=%d",
        len(client_script.setup_steps),
        len(client_script.execution_steps),
    )
    logger.info(
        "Executed steps: setup=%d, execution=%d",
        len(executed_script.pre_test_setup),
        len(executed_script.execution_steps),
    )

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
            logger.warning("[SETUP %s] Missing in executed PDF", step_num)

        else:
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure,
                })
                logger.warning(
                    "[SETUP %s] Procedure mismatch\nClient: %r\nExecuted: %r",
                    step_num,
                    client_step.procedure,
                    exec_step.procedure,
                )

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

        logger.info(
            "[EXEC %s] Starting comparison | pass_fail=%r",
            step_num,
            getattr(exec_step, "pass_fail", None),
        )

        if not exec_step:
            diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF",
            })
            logger.warning("[EXEC %s] Missing in executed PDF", step_num)

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
                logger.warning("[EXEC %s] Procedure mismatch", step_num)

            # 2️⃣ EXPECTED vs ACTUAL
            if expected == actual:
                logger.info("[EXEC %s] Expected == Actual (exact match)", step_num)

            elif allows_dynamic_suffix(expected) and actual.startswith(expected):
                diffs.append({
                    "type": "expected_with_dynamic_data",
                    "status": "PASS",
                    "expected": expected,
                    "actual": actual,
                    "dynamic_data": extract_dynamic_values(actual),
                })
                logger.info(
                    "[EXEC %s] Expected matched with dynamic data | actual=%r",
                    step_num,
                    actual,
                )

            else:
                diffs.append({
                    "type": "expected_vs_actual_mismatch",
                    "client_expected": expected,
                    "executed_actual": actual,
                })
                logger.error(
                    "[EXEC %s] Expected vs Actual mismatch\nExpected: %r\nActual: %r",
                    step_num,
                    expected,
                    actual,
                )

            # 3️⃣ PASS / FAIL (IMPORTANT FIX)
            # ❗ Only FAIL is a real issue
            if exec_step.pass_fail:
                if exec_step.pass_fail.upper() == "FAIL":
                    diffs.append({
                        "type": "execution_failed",
                        "status": "FAIL",
                    })
                    logger.error("[EXEC %s] Execution FAILED", step_num)
                else:
                    logger.info(
                        "[EXEC %s] Execution status=%s (ignored)",
                        step_num,
                        exec_step.pass_fail,
                    )
            else:
                logger.info(
                    "[EXEC %s] Execution status MISSING → ignored (NOT a failure)",
                    step_num,
                )

        if diffs:
            execution_differences[step_num] = diffs

    # =====================================================
    # ISSUE COUNTING (STEP LEVEL — CORRECT)
    # =====================================================
    REAL_FAILURE_TYPES = {
        "missing",
        "procedure_mismatch",
        "expected_vs_actual_mismatch",
        "execution_failed",
    }

    def count_steps_with_real_issues(
        differences: Dict[int, List[Dict[str, Any]]]
    ) -> int:
        """
        Count steps that have AT LEAST ONE real failure.
        """
        count = 0
        for step_num, step_diffs in differences.items():
            if any(d["type"] in REAL_FAILURE_TYPES for d in step_diffs):
                count += 1
                logger.info(
                    "[COUNT] Step %s counted as REAL ISSUE", step_num
                )
        return count

    total_setup_issues = count_steps_with_real_issues(setup_differences)
    total_execution_issues = count_steps_with_real_issues(execution_differences)
    total_issues = total_setup_issues + total_execution_issues

    logger.info("Comparison finished")
    logger.info(
        "Issue summary → setup=%d, execution=%d, total=%d",
        total_setup_issues,
        total_execution_issues,
        total_issues,
    )

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