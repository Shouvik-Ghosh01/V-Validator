from typing import List
from backend.compare.schemas import ClientScript, ExecutedScript


def _normalize(text: str) -> str:
    """Normalize text for safe comparison."""
    return (text or "").strip().lower()


def compare_scripts(
    client_script: ClientScript,
    executed_script: ExecutedScript,
) -> List[str]:
    """
    Compares client (input) PDF vs executed (V-Assure output) PDF.

    Rules:
    - Setup steps:
        • Compare step number + procedure text
    - Execution steps:
        • Compare expected results
        • PASS / FAIL must be PASS
    """

    diffs: List[str] = []

    # -----------------------------
    # SETUP STEP COMPARISON
    # -----------------------------
    client_setup = {s.step_number: s for s in client_script.setup_steps}
    executed_setup = {s.step_number: s for s in executed_script.pre_test_setup}

    for step_num, client_step in client_setup.items():
        exec_step = executed_setup.get(step_num)

        if not exec_step:
            diffs.append(f"[SETUP] Step {step_num} missing in executed PDF")
            continue

        if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
            diffs.append(
                f"[SETUP] Step {step_num} procedure mismatch\n"
                f"  Client: {client_step.procedure}\n"
                f"  Executed: {exec_step.procedure}"
            )

    # -----------------------------
    # EXECUTION STEP COMPARISON
    # -----------------------------
    client_exec = {s.step_number: s for s in client_script.execution_steps}
    executed_exec = {s.step_number: s for s in executed_script.execution_steps}

    for step_num, client_step in client_exec.items():
        exec_step = executed_exec.get(step_num)

        if not exec_step:
            diffs.append(f"[EXECUTION] Step {step_num} missing in executed PDF")
            continue

        # Expected results comparison
        if _normalize(client_step.expected_results) != _normalize(exec_step.expected_results):
            diffs.append(
                f"[EXECUTION] Step {step_num} expected result mismatch\n"
                f"  Client: {client_step.expected_results}\n"
                f"  Executed: {exec_step.expected_results}"
            )

        # PASS / FAIL must be PASS
        pass_fail = _normalize(exec_step.pass_fail)

        if pass_fail != "pass":
            diffs.append(
                f"[EXECUTION] Step {step_num} did not PASS\n"
                f"  Actual Result: {exec_step.actual_results or 'N/A'}\n"
                f"  Status: {exec_step.pass_fail or 'MISSING'}"
            )

    return diffs