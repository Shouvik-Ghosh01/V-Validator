from typing import List, Dict, Any
from backend.compare.schemas import ClientScript, ExecutedScript


def _normalize(text: str) -> str:
    """
    Normalize text for comparison - EXACT matching with basic cleanup only.
    Only strips leading/trailing whitespace and converts None to empty string.
    Does NOT lowercase or normalize internal spaces.
    """
    if text is None:
        return ""
    return text.strip()


def compare_scripts(
    client_script: ClientScript,
    executed_script: ExecutedScript,
) -> Dict[str, Any]:
    """
    Compares client (input) PDF vs executed (V-Assure output) PDF.

    Rules for each step:
    1. Compare procedure: Client → Executed (EXACT match)
    2. Compare expected results: Client → Executed (EXACT match)
    3. Compare expected results to actual results: Client Expected → Executed Actual (EXACT match)
    
    Returns structured comparison results with separate sections for setup and execution steps.
    """

    setup_differences = {}
    execution_differences = {}

    # -----------------------------
    # SETUP STEP COMPARISON
    # -----------------------------
    client_setup = {s.step_number: s for s in client_script.setup_steps}
    executed_setup = {s.step_number: s for s in executed_script.pre_test_setup}

    for step_num, client_step in client_setup.items():
        exec_step = executed_setup.get(step_num)

        step_diffs = []

        if not exec_step:
            step_diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF"
            })
        else:
            # Compare procedure - EXACT match
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                step_diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure
                })

        if step_diffs:
            setup_differences[step_num] = step_diffs

    # -----------------------------
    # EXECUTION STEP COMPARISON
    # -----------------------------
    client_exec = {s.step_number: s for s in client_script.execution_steps}
    executed_exec = {s.step_number: s for s in executed_script.execution_steps}

    for step_num, client_step in client_exec.items():
        exec_step = executed_exec.get(step_num)

        step_diffs = []

        if not exec_step:
            step_diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF"
            })
        else:
            # 1️⃣ Compare PROCEDURE: Client → Executed (EXACT match)
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                step_diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure
                })

            # 2️⃣ Compare EXPECTED RESULTS: Client → Executed (EXACT match)
            if _normalize(client_step.expected_results) != _normalize(exec_step.expected_results):
                step_diffs.append({
                    "type": "expected_mismatch",
                    "client": client_step.expected_results,
                    "executed": exec_step.expected_results
                })

            # 3️⃣ Compare CLIENT EXPECTED vs EXECUTED ACTUAL (EXACT match)
            if _normalize(client_step.expected_results) != _normalize(exec_step.actual_results):
                step_diffs.append({
                    "type": "expected_vs_actual",
                    "client_expected": client_step.expected_results,
                    "executed_actual": exec_step.actual_results
                })

        if step_diffs:
            execution_differences[step_num] = step_diffs

    # Calculate summary
    total_setup_issues = len(setup_differences)
    total_execution_issues = len(execution_differences)
    total_issues = total_setup_issues + total_execution_issues

    return {
        "has_differences": total_issues > 0,
        "summary": {
            "total_issues": total_issues,
            "setup_steps_with_issues": total_setup_issues,
            "execution_steps_with_issues": total_execution_issues
        },
        "setup_differences": setup_differences,
        "execution_differences": execution_differences
    }