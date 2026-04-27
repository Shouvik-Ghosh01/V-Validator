from typing import Dict, Any, List
import logging
import re

from compare.schemas import ClientScript, ExecutedScript
from compare.dynamic_rules import (
    allows_dynamic_suffix,
    extract_dynamic_values,
)

# ------------------------------------------------------------------
# Logger setup
# ------------------------------------------------------------------
logger = logging.getLogger("pdf_comparator")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# ------------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------------
def log_block(title: str, content):
    logger.info("---- %s ----", title)
    if isinstance(content, dict):
        for k, v in content.items():
            logger.info("%s → %s", k, v)
    elif isinstance(content, list):
        for v in content:
            logger.info("- %s", v)
    else:
        logger.info("%s", content if content else "<EMPTY>")
    logger.info("---- END %s ----", title)


# =====================================================
# SETUP STEP 1 – ENSURE ACCOUNT HANDLING
# =====================================================
EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def normalize_role_name(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[•\-]", " ", text)
    text = text.replace("/", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_roles_from_client(text: str) -> List[str]:
    roles = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("-"):
            roles.append(normalize_role_name(line))
    return roles


def extract_roles_and_emails_from_exec(text: str) -> Dict[str, str]:
    result = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        email_match = re.search(EMAIL_REGEX, line)
        if email_match:
            email = email_match.group(0)
            role_part = line.split(":")[0]
            role = normalize_role_name(role_part)
            result[role] = email
    return result


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _normalize(text: str) -> str:
    return (text or "").strip()


# ------------------------------------------------------------------
# Main comparator
# ------------------------------------------------------------------
def compare_scripts(
    client_script: ClientScript,
    executed_script: ExecutedScript,
) -> Dict[str, Any]:

    setup_differences: Dict[int, List[Dict[str, Any]]] = {}
    execution_differences: Dict[int, List[Dict[str, Any]]] = {}

    logger.info("Starting PDF comparison")

    # =====================================================
    # SETUP STEP COMPARISON
    # =====================================================
    client_setup = {s.step_number: s for s in client_script.setup_steps}
    executed_setup = {s.step_number: s for s in executed_script.pre_test_setup}

    for step_num, client_step in client_setup.items():
        exec_step = executed_setup.get(step_num)
        diffs = []

        logger.info("[SETUP %s] Comparing setup step", step_num)

        if not exec_step:
            logger.warning("[SETUP %s] Missing in executed PDF", step_num)
            diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF",
            })

        # -------------------------------------------------
        # STEP 1 – ENSURE THE FOLLOWING
        # -------------------------------------------------
        elif (
            step_num == 1
            and client_step.procedure.lower().startswith("ensure the following")
        ):
            logger.info("[SETUP 1] Detected ENSURE THE FOLLOWING step")

            log_block("SETUP 1 CLIENT RAW", client_step.procedure)
            log_block("SETUP 1 EXEC RAW", exec_step.procedure)

            client_roles = extract_roles_from_client(client_step.procedure)
            exec_roles_emails = extract_roles_and_emails_from_exec(exec_step.procedure)

            log_block("SETUP 1 CLIENT ROLES", client_roles)
            log_block("SETUP 1 EXEC ROLES → EMAILS", exec_roles_emails)

            missing_roles = [
                role for role in client_roles
                if role not in exec_roles_emails
            ]

            if missing_roles:
                logger.warning("[SETUP 1] Missing roles detected")
                log_block("SETUP 1 MISSING ROLES", missing_roles)

                diffs.append({
                    "type": "ensure_account_missing",
                    "missing_roles": missing_roles,
                    "client": client_step.procedure,
                    "executed": exec_step.procedure,
                })
            else:
                logger.info("[SETUP 1] Accounts validated with runtime emails")

                diffs.append({
                    "type": "ensure_accounts_with_dynamic_data",
                    "status": "PASS",
                    "accounts": exec_roles_emails,
                })

        # -------------------------------------------------
        # NORMAL SETUP STEPS
        # -------------------------------------------------
        else:
            client_norm = _normalize(client_step.procedure)
            exec_norm = _normalize(exec_step.procedure)

            if client_norm != exec_norm:
                logger.warning("[SETUP %s] Procedure mismatch", step_num)

                log_block(f"SETUP {step_num} CLIENT RAW", client_step.procedure)
                log_block(f"SETUP {step_num} EXEC RAW", exec_step.procedure)
                log_block(f"SETUP {step_num} CLIENT NORMALIZED", client_norm)
                log_block(f"SETUP {step_num} EXEC NORMALIZED", exec_norm)

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

        logger.info("[EXEC %s] Comparing execution step", step_num)

        if not exec_step:
            logger.warning("[EXEC %s] Missing in executed PDF", step_num)
            diffs.append({
                "type": "missing",
                "message": "Step missing in executed PDF",
            })

        else:
            if _normalize(client_step.procedure) != _normalize(exec_step.procedure):
                logger.warning("[EXEC %s] Procedure mismatch", step_num)

                log_block(f"EXEC {step_num} CLIENT PROC", client_step.procedure)
                log_block(f"EXEC {step_num} EXEC PROC", exec_step.procedure)

                diffs.append({
                    "type": "procedure_mismatch",
                    "client": client_step.procedure,
                    "executed": exec_step.procedure,
                })

            expected = _normalize(client_step.expected_results)
            actual = _normalize(exec_step.actual_results)

            if expected == actual:
                logger.info("[EXEC %s] Expected == Actual", step_num)

            elif allows_dynamic_suffix(expected) and actual.startswith(expected):
                logger.info("[EXEC %s] Dynamic suffix accepted", step_num)

                diffs.append({
                    "type": "expected_with_dynamic_data",
                    "status": "PASS",
                    "expected": expected,
                    "actual": actual,
                    "dynamic_data": extract_dynamic_values(actual),
                })

            else:
                logger.error("[EXEC %s] Expected vs Actual mismatch", step_num)

                log_block(f"EXEC {step_num} EXPECTED", expected)
                log_block(f"EXEC {step_num} ACTUAL", actual)

                diffs.append({
                    "type": "expected_vs_actual_mismatch",
                    "client_expected": expected,
                    "executed_actual": actual,
                })

            if exec_step.pass_fail and exec_step.pass_fail.upper() == "FAIL":
                logger.error("[EXEC %s] Execution FAILED", step_num)
                diffs.append({
                    "type": "execution_failed",
                    "status": "FAIL",
                })

        if diffs:
            execution_differences[step_num] = diffs

    # =====================================================
    # ISSUE COUNTING
    # =====================================================
    REAL_FAILURE_TYPES = {
        "missing",
        "procedure_mismatch",
        "expected_vs_actual_mismatch",
        "execution_failed",
        "ensure_account_missing",
    }

    def count_real_steps(differences):
        count = 0
        for step_num, step_diffs in differences.items():
            real = [d["type"] for d in step_diffs if d["type"] in REAL_FAILURE_TYPES]
            if real:
                logger.info("[COUNT] Step %s counted | reasons=%s", step_num, real)
                count += 1
            else:
                logger.info("[COUNT] Step %s ignored (no real failures)", step_num)
        return count

    total_setup = count_real_steps(setup_differences)
    total_exec = count_real_steps(execution_differences)

    logger.info(
        "Finished comparison | setup=%d execution=%d total=%d",
        total_setup,
        total_exec,
        total_setup + total_exec,
    )

    return {
        "has_differences": (total_setup + total_exec) > 0,
        "summary": {
            "total_issues": total_setup + total_exec,
            "setup_steps_with_issues": total_setup,
            "execution_steps_with_issues": total_exec,
        },
        "setup_differences": setup_differences,
        "execution_differences": execution_differences,
    }