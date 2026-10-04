"""
comparator_output.py
~~~~~~~~~~~~~~~~~~~~
Output-vs-Output (peer) comparison of two V-Assure *executed* reports.

    ExecutedScript (Output A)  ─┐
                                ├─►  compare_execution_reports()  ─►  differences
    ExecutedScript (Output B)  ─┘

This is NOT an expected-vs-actual validation. Neither side is "correct", so the
vocabulary here is deliberately neutral:

    changed     value exists on both sides and differs
    missing     present in Output A, absent from Output B
    additional  absent from Output A, present in Output B
    identical   (only counted, not listed, unless include_identical=True)
    ambiguous   step numbers line up but the content is too different to confirm
                they are the same logical step

The Template-vs-Output engine in comparator.py is untouched; this module only
reuses its account-parsing helpers.

Runtime-generated values
------------------------
Two runs legitimately produce different generated values (record names, ids,
account emails). A difference is flagged ``runtime_generated=True`` ONLY when
every difference between the two texts is a value recognised by
dynamic_rules.DYNAMIC_VALUE_PATTERNS *and* the two values have the same shape
once digit runs are collapsed (Product_12345 vs Product_12387). Anything else —
including Product_1 vs Vendor_1 — stays a meaningful difference.

Runtime-generated differences are still listed, but are excluded from
``summary.total_differences`` / ``has_differences``.

step_number convention
----------------------
``step_number`` is Output A's number for every type except ``additional``,
where it is Output B's number. When two steps were paired by procedure text
instead of by number, ``output_b_step_number`` carries B's number.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

from compare.comparator import (
    extract_roles_and_emails_from_exec,  # reused, not modified
)
from compare.dynamic_rules import dynamic_value_shape, mask_dynamic_values
from compare.schemas import (
    DIFF_ADDITIONAL,
    DIFF_AMBIGUOUS,
    DIFF_CHANGED,
    DIFF_IDENTICAL,
    DIFF_MISSING,
    ExecutedExecutionStep,
    ExecutedScript,
    SetupStep,
)

logger = logging.getLogger("pdf_comparator.output")

# ------------------------------------------------------------------
# Tunables
# ------------------------------------------------------------------

# Metadata that is per-run by nature. Still listed as "changed", but flagged
# runtime_generated and kept out of the headline totals — otherwise two runs of
# the same script would ALWAYS report differences.
RUN_SPECIFIC_METADATA = {"run_number", "start_time", "end_time", "script_run_time"}

# Stable display order for metadata keys that the executed extractor produces.
METADATA_ORDER = [
    "script_id",
    "title",
    "description",
    "build_number",
    "vault_name",
    "product_version",
    "v_assure_environment",
    "run_number",
    "start_time",
    "end_time",
    "script_run_time",
]

# Procedure-text similarity (difflib ratio, dynamic values masked).
#   number-matched pair below AMBIGUOUS_SIMILARITY -> identity of the step is in doubt
#   two doubtful/unmatched steps at or above REANCHOR_SIMILARITY -> same logical step,
#   renumbered.
AMBIGUOUS_SIMILARITY = 0.60
REANCHOR_SIMILARITY = 0.85

FIELD_LABELS = {
    "procedure": "Procedure",
    "expected_results": "Expected results text",
    "actual_results": "Actual results",
    "pass_fail": "Status",
}


# ------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------
def _norm(text: Optional[str]) -> str:
    """Whitespace-insensitive form used for equality checks."""
    return " ".join((text or "").split())


def _similarity(a: str, b: str) -> float:
    """Procedure similarity in [0, 1], ignoring runtime-generated values."""
    ma = _norm(mask_dynamic_values(a)[0]).lower()
    mb = _norm(mask_dynamic_values(b)[0]).lower()
    if ma == mb:
        return 1.0
    # autojunk=False matters: with the default (True), any text >= 200 chars
    # treats frequent characters as junk and the ratio collapses, so two nearly
    # identical long procedures would look unrelated.
    return SequenceMatcher(None, ma, mb, autojunk=False).ratio()


def _is_runtime_generated_text_diff(a: str, b: str) -> bool:
    """
    True only when a and b differ solely in runtime-generated values of the same shape.
    """
    ma, va = mask_dynamic_values(a)
    mb, vb = mask_dynamic_values(b)

    if _norm(ma) != _norm(mb):
        return False  # something other than a generated value differs
    if va.keys() != vb.keys():
        return False

    for key in va:
        if len(va[key]) != len(vb[key]):
            return False
        for x, y in zip(va[key], vb[key]):
            if dynamic_value_shape(x) != dynamic_value_shape(y):
                return False

    return bool(va)  # masked-equal but nothing was masked would mean a == b


class _Collector:
    """Accumulates differences and counters for one comparison."""

    def __init__(self, include_identical: bool = False):
        self.include_identical = include_identical
        self.differences: List[Dict[str, Any]] = []
        self.identical_setup_steps = 0
        self.identical_execution_steps = 0
        self._n = 0

    def mark_identical(self, scope: str, step_number: int) -> None:
        """Count an identical step; list it only when include_identical is set."""
        if scope == "setup":
            self.identical_setup_steps += 1
        else:
            self.identical_execution_steps += 1
        if self.include_identical:
            self.add(scope=scope, type=DIFF_IDENTICAL, field="step", step_number=step_number,
                     message=f"Step {step_number} is identical in Output A and Output B")

    def add(
        self,
        *,
        scope: str,
        type: str,
        field: Optional[str] = None,
        step_number: Optional[int] = None,
        output_a: Optional[str] = None,
        output_b: Optional[str] = None,
        message: str = "",
        runtime_generated: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        self._n += 1
        diff: Dict[str, Any] = {
            "id": f"diff-{self._n:03d}",
            "scope": scope,
            "step_number": step_number,
            "field": field,
            "type": type,
            "output_a": output_a,
            "output_b": output_b,
            "message": message,
            "runtime_generated": runtime_generated,
        }
        diff.update(extra)
        self.differences.append(diff)
        return diff


# ------------------------------------------------------------------
# Step alignment
# ------------------------------------------------------------------
Pair = Tuple[Optional[Any], Optional[Any], str]  # (a, b, matched_by)
MATCHED_BY_NUMBER = "step_number"
MATCHED_BY_TEXT = "procedure_similarity"
MATCHED_AMBIGUOUS = "step_number_ambiguous"


def align_steps(
    a_steps: List[Any],
    b_steps: List[Any],
    text_of: Callable[[Any], str] = lambda s: s.procedure,
) -> List[Pair]:
    """
    Pair up steps from two reports without relying on array position.

    1. Steps sharing a step_number are paired, if their procedure text is
       plausibly the same step (similarity >= AMBIGUOUS_SIMILARITY).
    2. Number-matched pairs that fail that check, plus steps whose number exists
       on one side only, are re-paired by procedure text (>= REANCHOR_SIMILARITY,
       best match first). This recovers renumbered steps.
    3. Number-matched pairs still unresolved are kept as *ambiguous* pairs.
    4. Whatever is left is missing (A only) or additional (B only).

    Returns pairs as (a, b, matched_by); a is None for additional steps and b is
    None for missing steps.
    """
    a_by = {s.step_number: s for s in a_steps}
    b_by = {s.step_number: s for s in b_steps}

    pairs: List[Pair] = []
    doubtful: List[int] = []  # step numbers present on both sides but suspicious

    for n in sorted(set(a_by) & set(b_by)):
        if _similarity(text_of(a_by[n]), text_of(b_by[n])) >= AMBIGUOUS_SIMILARITY:
            pairs.append((a_by[n], b_by[n], MATCHED_BY_NUMBER))
        else:
            doubtful.append(n)

    free_a = [a_by[n] for n in sorted(a_by) if n not in b_by] + [a_by[n] for n in doubtful]
    free_b = [b_by[n] for n in sorted(b_by) if n not in a_by] + [b_by[n] for n in doubtful]

    candidates = []
    for a in free_a:
        for b in free_b:
            sim = _similarity(text_of(a), text_of(b))
            if sim >= REANCHOR_SIMILARITY:
                candidates.append((sim, a, b))
    candidates.sort(key=lambda t: (-t[0], t[1].step_number, t[2].step_number))

    used_a: set = set()
    used_b: set = set()
    for _sim, a, b in candidates:
        if a.step_number in used_a or b.step_number in used_b:
            continue
        used_a.add(a.step_number)
        used_b.add(b.step_number)
        pairs.append((a, b, MATCHED_BY_NUMBER if a.step_number == b.step_number else MATCHED_BY_TEXT))

    for n in doubtful:
        if n not in used_a and n not in used_b:
            pairs.append((a_by[n], b_by[n], MATCHED_AMBIGUOUS))
            used_a.add(n)
            used_b.add(n)

    for a in free_a:
        if a.step_number not in used_a:
            pairs.append((a, None, ""))
    for b in free_b:
        if b.step_number not in used_b:
            pairs.append((None, b, ""))

    def _sort_key(p: Pair):
        a, b, _ = p
        return (a.step_number if a is not None else b.step_number, 0 if a is not None else 1)

    return sorted(pairs, key=_sort_key)


# ------------------------------------------------------------------
# Field-level comparison
# ------------------------------------------------------------------
def _compare_text_field(
    out: _Collector,
    *,
    scope: str,
    step_number: int,
    field: str,
    a_text: str,
    b_text: str,
    extra: Dict[str, Any],
) -> bool:
    """Compare one text field. Returns True if identical (whitespace-insensitive)."""
    if _norm(a_text) == _norm(b_text):
        return True

    label = FIELD_LABELS.get(field, field)
    runtime = _is_runtime_generated_text_diff(a_text, b_text)
    extra = dict(extra)

    if runtime:
        _, va = mask_dynamic_values(a_text)
        _, vb = mask_dynamic_values(b_text)
        extra["dynamic_values"] = {"output_a": va, "output_b": vb}
        message = f"{label} changed only in runtime-generated values"
    else:
        message = f"{label} changed between Output A and Output B"

    out.add(
        scope=scope,
        type=DIFF_CHANGED,
        field=field,
        step_number=step_number,
        output_a=a_text,
        output_b=b_text,
        message=message,
        runtime_generated=runtime,
        **extra,
    )
    return False


def _compare_status(
    out: _Collector, *, step_number: int, a_val: str, b_val: str, extra: Dict[str, Any]
) -> bool:
    a_s, b_s = (a_val or "").strip().upper(), (b_val or "").strip().upper()
    if a_s == b_s:
        return True
    out.add(
        scope="execution",
        type=DIFF_CHANGED,
        field="pass_fail",
        step_number=step_number,
        output_a=a_s or None,
        output_b=b_s or None,
        message=f"Status changed: {a_s or '(none)'} → {b_s or '(none)'}",
        **extra,
    )
    return False


def _pair_extra(a: Any, b: Any, matched_by: str) -> Dict[str, Any]:
    extra: Dict[str, Any] = {"matched_by": matched_by}
    if a.step_number != b.step_number:
        extra["output_b_step_number"] = b.step_number
    return extra


# ------------------------------------------------------------------
# Metadata
# ------------------------------------------------------------------
def _compare_metadata(out: _Collector, meta_a: Dict[str, Any], meta_b: Dict[str, Any]) -> None:
    keys = [k for k in METADATA_ORDER if k in meta_a or k in meta_b]
    keys += sorted((set(meta_a) | set(meta_b)) - set(METADATA_ORDER))

    for key in keys:
        in_a, in_b = key in meta_a, key in meta_b
        va = None if not in_a else str(meta_a[key])
        vb = None if not in_b else str(meta_b[key])
        run_specific = key in RUN_SPECIFIC_METADATA

        if in_a and not in_b:
            out.add(scope="metadata", type=DIFF_MISSING, field=key, output_a=va,
                    message=f"'{key}' is present in Output A but not in Output B",
                    runtime_generated=run_specific)
        elif in_b and not in_a:
            out.add(scope="metadata", type=DIFF_ADDITIONAL, field=key, output_b=vb,
                    message=f"'{key}' is present in Output B but not in Output A",
                    runtime_generated=run_specific)
        elif _norm(va) != _norm(vb):
            out.add(scope="metadata", type=DIFF_CHANGED, field=key, output_a=va, output_b=vb,
                    message=(f"Run-specific value changed: {va} → {vb}" if run_specific
                             else f"Value changed: {va} → {vb}"),
                    runtime_generated=run_specific)


# ------------------------------------------------------------------
# Setup (PTS)
# ------------------------------------------------------------------
def _is_accounts_step(step: SetupStep) -> bool:
    return step.step_number == 1 and step.procedure.lower().startswith("ensure the following")


def _account_map(procedure: str) -> Dict[str, Tuple[str, str]]:
    """{account name -> (full normalised definition, email)}, keeping duplicates apart."""
    result: Dict[str, Tuple[str, str]] = {}
    for definition, email in extract_roles_and_emails_from_exec(procedure).items():
        name = definition.split("(")[0].strip()
        key, n = name, 1
        while key in result:
            n += 1
            key = f"{name} #{n}"
        result[key] = (definition, email)
    return result


def _email_shape(email: str) -> str:
    return re.sub(r"\d+", "#", (email or "").strip().lower())


def _compare_accounts(out: _Collector, a: SetupStep, b: SetupStep, extra: Dict[str, Any]) -> bool:
    """
    Peer comparison of the 'Ensure the following accounts' setup step.

    Same account + same definition + different email  -> runtime-generated when the
    emails differ only by digits; otherwise a meaningful change.
    Same account + different definition               -> meaningful change.
    """
    accts_a, accts_b = _account_map(a.procedure), _account_map(b.procedure)
    identical = True

    for name in accts_a:
        if name not in accts_b:
            identical = False
            out.add(scope="setup", type=DIFF_MISSING, field="account", step_number=a.step_number,
                    output_a=accts_a[name][0],
                    message=f"Account '{name}' is present in Output A but not in Output B", **extra)
            continue

        def_a, email_a = accts_a[name]
        def_b, email_b = accts_b[name]

        if def_a != def_b:
            identical = False
            out.add(scope="setup", type=DIFF_CHANGED, field="account_definition",
                    step_number=a.step_number, output_a=def_a, output_b=def_b,
                    message=f"Definition of account '{name}' differs between Output A and Output B",
                    **extra)

        if email_a != email_b:
            identical = False
            digits_only = _email_shape(email_a) == _email_shape(email_b)
            out.add(scope="setup", type=DIFF_CHANGED, field="account_email",
                    step_number=a.step_number, output_a=email_a, output_b=email_b,
                    message=(f"Account '{name}': email differs only by digits "
                             "(runtime-generated)" if digits_only
                             else f"Account '{name}': email differs"),
                    runtime_generated=digits_only, **extra)

    for name in accts_b:
        if name not in accts_a:
            identical = False
            out.add(scope="setup", type=DIFF_ADDITIONAL, field="account", step_number=b.step_number,
                    output_b=accts_b[name][0],
                    message=f"Account '{name}' is present in Output B but not in Output A", **extra)

    return identical


def _compare_setup(out: _Collector, a_steps: List[SetupStep], b_steps: List[SetupStep]) -> None:
    for a, b, matched_by in align_steps(a_steps, b_steps):
        if b is None:
            out.add(scope="setup", type=DIFF_MISSING, field="step", step_number=a.step_number,
                    output_a=a.procedure,
                    message=f"Setup step {a.step_number} is present in Output A but not in Output B")
            continue
        if a is None:
            out.add(scope="setup", type=DIFF_ADDITIONAL, field="step", step_number=b.step_number,
                    output_b=b.procedure,
                    message=f"Setup step {b.step_number} is present in Output B but not in Output A")
            continue

        if matched_by == MATCHED_AMBIGUOUS:
            out.add(scope="setup", type=DIFF_AMBIGUOUS, field="procedure", step_number=a.step_number,
                    output_a=a.procedure, output_b=b.procedure,
                    message=(f"Setup step {a.step_number} exists in both outputs but the procedures "
                             "differ substantially; they may not be the same step"),
                    matched_by=matched_by)
            continue

        extra = _pair_extra(a, b, matched_by)
        identical = True

        if a.step_number != b.step_number:
            identical = False
            out.add(scope="setup", type=DIFF_CHANGED, field="step_number", step_number=a.step_number,
                    output_a=str(a.step_number), output_b=str(b.step_number),
                    message=(f"Setup step {a.step_number} in Output A matches step {b.step_number} "
                             "in Output B by procedure text"), **extra)

        if (_is_accounts_step(a) and _is_accounts_step(b)
                and _account_map(a.procedure) and _account_map(b.procedure)):
            identical &= _compare_accounts(out, a, b, extra)
        else:
            identical &= _compare_text_field(
                out, scope="setup", step_number=a.step_number, field="procedure",
                a_text=a.procedure, b_text=b.procedure, extra=extra)

        if identical:
            out.mark_identical("setup", a.step_number)


# ------------------------------------------------------------------
# Execution steps
# ------------------------------------------------------------------
def _compare_execution(
    out: _Collector,
    a_steps: List[ExecutedExecutionStep],
    b_steps: List[ExecutedExecutionStep],
) -> None:
    for a, b, matched_by in align_steps(a_steps, b_steps):
        if b is None:
            out.add(scope="execution", type=DIFF_MISSING, field="step", step_number=a.step_number,
                    output_a=a.procedure,
                    message=f"Step {a.step_number} is present in Output A but not in Output B")
            continue
        if a is None:
            out.add(scope="execution", type=DIFF_ADDITIONAL, field="step", step_number=b.step_number,
                    output_b=b.procedure,
                    message=f"Step {b.step_number} is present in Output B but not in Output A")
            continue

        if matched_by == MATCHED_AMBIGUOUS:
            out.add(scope="execution", type=DIFF_AMBIGUOUS, field="procedure",
                    step_number=a.step_number, output_a=a.procedure, output_b=b.procedure,
                    message=(f"Step {a.step_number} exists in both outputs but the procedures differ "
                             "substantially; they may not be the same step, so its results were "
                             "not compared"),
                    matched_by=matched_by)
            continue

        extra = _pair_extra(a, b, matched_by)
        identical = True

        if a.step_number != b.step_number:
            identical = False
            out.add(scope="execution", type=DIFF_CHANGED, field="step_number",
                    step_number=a.step_number, output_a=str(a.step_number),
                    output_b=str(b.step_number),
                    message=(f"Step {a.step_number} in Output A matches step {b.step_number} "
                             "in Output B by procedure text"), **extra)

        for fld in ("procedure", "expected_results", "actual_results"):
            identical &= _compare_text_field(
                out, scope="execution", step_number=a.step_number, field=fld,
                a_text=getattr(a, fld), b_text=getattr(b, fld), extra=extra)

        identical &= _compare_status(
            out, step_number=a.step_number, a_val=a.pass_fail, b_val=b.pass_fail, extra=extra)

        if identical:
            out.mark_identical("execution", a.step_number)


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------
def compare_execution_reports(
    output_a: ExecutedScript,
    output_b: ExecutedScript,
    *,
    include_identical: bool = False,
) -> Dict[str, Any]:
    """
    Compare two executed reports as peers.

    Both arguments MUST be ExecutedScript objects (produced by
    extract_executed_pdf). This function has no client/template path.
    """
    out = _Collector(include_identical=include_identical)

    _compare_metadata(out, output_a.metadata, output_b.metadata)
    _compare_setup(out, output_a.pre_test_setup, output_b.pre_test_setup)
    _compare_execution(out, output_a.execution_steps, output_b.execution_steps)

    real = [d for d in out.differences if d["type"] != DIFF_IDENTICAL]
    meaningful = [d for d in real if not d["runtime_generated"]]
    runtime = [d for d in real if d["runtime_generated"]]

    def _count(t: str) -> int:
        return sum(1 for d in meaningful if d["type"] == t)

    def _steps_with(scope: str) -> int:
        return len({d["step_number"] for d in meaningful if d["scope"] == scope})

    summary = {
        "total_differences": len(meaningful),
        "changed": _count(DIFF_CHANGED),
        "missing": _count(DIFF_MISSING),
        "additional": _count(DIFF_ADDITIONAL),
        "ambiguous": _count(DIFF_AMBIGUOUS),
        "runtime_generated_differences": len(runtime),
        "metadata_differences": sum(1 for d in meaningful if d["scope"] == "metadata"),
        "setup_steps_with_differences": _steps_with("setup"),
        "execution_steps_with_differences": _steps_with("execution"),
        "identical_setup_steps": out.identical_setup_steps,
        "identical_execution_steps": out.identical_execution_steps,
    }

    logger.info(
        "Output-vs-Output comparison finished | meaningful=%d runtime_generated=%d",
        len(meaningful), len(runtime),
    )

    return {
        "comparison_mode": "output_vs_output",
        "has_differences": len(meaningful) > 0,
        "summary": summary,
        "differences": out.differences,
    }
