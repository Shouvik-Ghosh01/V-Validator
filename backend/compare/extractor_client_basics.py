"""
extractor_client_basics.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Extractor for the Veeva Basics "Pre-Approved Test Script" client PDF format.

PDF layout (per file reviewed):
  Page 1  – Cover page: Script ID + Script Title only. No table data.
  Page 2  – Single metadata table with labeled rows:
               Row keys (left col): Test Script ID, Description, Vault Name,
                                    V-Assure Environment, Start Time,
                                    Pre-Test Setup (PTS)
               Row keys (right col): Title, Build Number, Product Version,
                                     Run Number, End Time
             The Pre-Test Setup (PTS) cell holds the BEGINNING of all setup
             steps.  Because the PTS content is a single merged cell spanning
             multiple pages, pdfplumber truncates it at the page boundary.
  Page 3+ – PTS CONTINUATION pages: pdfplumber surfaces these as single-row
             tables with an empty col 0 and the remaining PTS text in col 1.
             These pages must be stitched together with the page-2 PTS text
             BEFORE parsing individual steps.
             Pages continue to be PTS continuation until either:
               (a) a non-continuation table is encountered (execution table), or
               (b) an explicit PTS "end sentinel" is detected (the last PTS
                   phrase in the document, i.e. "all active Content Plan Items
                   have a green harvey ball icon").
  Execution pages – Step # | Procedure | Expected Results |
                    Actual Results | Pass/Fail
  Last page – Script Pre-Approval / Execution Approval signatures (ignored).

Return type: ClientScript  (same schema as before – no downstream changes needed)

Bug fixed (original): _is_metadata_table previously scanned ALL cells in each
row, causing tables on continuation pages to be mis-classified as metadata when
an expected-result cell contained the phrase "pre-test setup". Fix: only inspect
column 0 (the label/key column).

Ordering fix (original): _is_execution_table is checked BEFORE _is_metadata_table
in the main loop.

New fix: PTS content that spans across page boundaries is now fully stitched
together.  After the page-2 metadata table is processed, subsequent pages whose
FIRST non-header table has an empty col-0 and non-empty col-1 are treated as
PTS continuation pages and their col-1 content is appended to the PTS text
before parsing.
"""

import re
import pdfplumber

from compare.schemas import (
    SetupStep,
    ClientExecutionStep,
    ClientScript,
)
from compare.text_parsers import normalize_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXEC_HEADER_KEYWORDS = {"procedure", "expected results", "pass"}

META_KEYS = {
    "test script id":      "script_id",
    "title":               "title",
    "description":         "description",
    "build number":        "build_number",
    "vault name":          "vault_name",
    "product version":     "product_version",
    "v-assure environment":"v_assure_environment",
    "run number":          "run_number",
    "start time":          "start_time",
    "end time":            "end_time",
}

PTS_KEY_PATTERN = re.compile(r"pre.?test\s+setup", re.IGNORECASE)

_SKIP_VALUES = {
    "pass", "fail", "n/a", "yes", "no",
    "pass / fail / n/a", "pass/fail",
}

# Sentinel: last known phrase at the end of PTS content.
# When a continuation page's col-1 text ends with (or contains) this, we know
# we've collected all PTS pages.
_PTS_END_SENTINEL = re.compile(
    r"all active content plan items have a green harvey ball",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def _clean_cell(cell) -> str:
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_exec_cell(cell) -> str:
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Table-type detection
# ---------------------------------------------------------------------------

def _is_execution_table(table) -> bool:
    if not table or not table[0]:
        return False
    header = " ".join(str(c or "").lower() for c in table[0])
    hits = sum(1 for kw in EXEC_HEADER_KEYWORDS if kw in header)
    return hits >= 2


def _is_metadata_table(table) -> bool:
    """
    True when this is the page-2 metadata / Pre-Test Setup table.
    Only column 0 is inspected to avoid false positives.
    """
    if not table:
        return False
    for row in table[:8]:
        if not row:
            continue
        label = re.sub(r"\s+", " ", str(row[0] or "")).strip().lower()
        if "test script id" in label or "pre-test setup" in label:
            return True
    return False


def _is_pts_continuation_table(table) -> bool:
    """
    True when pdfplumber has surfaced a cross-page slice of the merged PTS
    cell as a standalone table.

    Pattern: single data row, col 0 is empty, col 1 has substantial text.
    The table may also have a one-row header like "Script ID : XXXXX" at
    index 0, so we look at all rows.
    """
    if not table:
        return False
    for row in table:
        if not row or len(row) < 2:
            continue
        col0 = str(row[0] or "").strip()
        col1 = str(row[1] or "").strip()
        if col0 == "" and len(col1) > 30:
            return True
    return False


# ---------------------------------------------------------------------------
# Metadata + PTS extraction (page 2 table)
# ---------------------------------------------------------------------------

def _extract_metadata_and_pts(table) -> tuple[dict, str]:
    metadata: dict = {}
    pts_text: str = ""

    for row in table:
        if not row:
            continue

        cells = [_clean_cell(c) for c in row]

        if PTS_KEY_PATTERN.search(cells[0] if cells else ""):
            value_parts = [cells[j] for j in range(1, len(cells)) if cells[j]]
            pts_text = "\n".join(value_parts).strip()
            continue

        pairs: list[tuple[str, str]] = []
        if len(cells) >= 2:
            pairs.append((cells[0], cells[1]))
        if len(cells) >= 4:
            pairs.append((cells[2], cells[3]))

        for key_raw, value in pairs:
            key_norm = re.sub(r"\s+", " ", key_raw.lower()).strip().rstrip(":")
            if key_norm in META_KEYS and value:
                metadata[META_KEYS[key_norm]] = value

    return metadata, pts_text


def _extract_pts_continuation(table) -> str:
    """Extract the PTS continuation text from a cross-page overflow table."""
    for row in table:
        if not row or len(row) < 2:
            continue
        col0 = str(row[0] or "").strip()
        col1 = str(row[1] or "").strip()
        if col0 == "" and len(col1) > 30:
            return col1
    return ""


# ---------------------------------------------------------------------------
# Pre-Test Setup parsing
# ---------------------------------------------------------------------------

def _parse_pts_steps(pts_text: str) -> list[SetupStep]:
    if not pts_text:
        return []

    steps: list[SetupStep] = []
    chunks = re.split(r"(?=^\s*\d+\.)", pts_text, flags=re.MULTILINE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        m = re.match(r"^(\d+)\.\s*(.*)", chunk, re.DOTALL)
        if not m:
            continue

        step_num = int(m.group(1))
        body = m.group(2).strip()

        lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in body.splitlines()
            if line.strip()
        ]
        procedure = "\n".join(lines)

        if procedure:
            steps.append(SetupStep(step_number=step_num, procedure=procedure))

    return steps


# ---------------------------------------------------------------------------
# Execution steps parsing
# ---------------------------------------------------------------------------

def _parse_execution_table(table) -> list[ClientExecutionStep]:
    steps: list[ClientExecutionStep] = []

    if not table or not table[0]:
        return steps

    header = [str(c or "").strip().lower() for c in table[0]]
    procedure_col: int | None = None
    expected_col: int | None = None

    for idx, h in enumerate(header):
        if "procedure" in h and procedure_col is None:
            procedure_col = idx
        if "expected" in h and expected_col is None:
            expected_col = idx

    for row in table[1:]:
        if not row:
            continue

        cells = [_clean_exec_cell(c) for c in row]
        non_empty = [(i, c) for i, c in enumerate(cells) if c]

        if not non_empty:
            continue

        step_num: int | None = None
        step_idx: int | None = None
        for i, c in non_empty:
            if c.isdigit():
                step_num = int(c)
                step_idx = i
                break

        if step_num is None:
            continue

        procedure = ""
        expected_results = ""

        if procedure_col is not None and procedure_col < len(cells):
            procedure = cells[procedure_col]
        if expected_col is not None and expected_col < len(cells):
            expected_results = cells[expected_col]

        if not procedure:
            content = [
                c for i, c in non_empty
                if i > (step_idx or 0) and c.lower() not in _SKIP_VALUES
            ]
            if content:
                procedure = content[0]
            if len(content) >= 2:
                expected_results = content[1]

        if procedure:
            steps.append(ClientExecutionStep(
                step_number=step_num,
                procedure=normalize_text(procedure),
                expected_results=normalize_text(expected_results),
            ))

    return steps


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_setup(steps: list[SetupStep]) -> list[SetupStep]:
    seen: dict[int, SetupStep] = {}
    for s in steps:
        if s.step_number not in seen:
            seen[s.step_number] = s
    return sorted(seen.values(), key=lambda x: x.step_number)


def _dedup_exec(steps: list[ClientExecutionStep]) -> list[ClientExecutionStep]:
    seen: dict[int, ClientExecutionStep] = {}
    for s in steps:
        if s.step_number not in seen:
            seen[s.step_number] = s
    return sorted(seen.values(), key=lambda x: x.step_number)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_client_pdf(pdf_path: str) -> ClientScript:
    """
    Extract a Veeva Basics Pre-Approved Test Script (client/template) PDF.

    Returns a ClientScript compatible with the existing comparator.
    """
    setup_steps: list[SetupStep] = []
    execution_steps: list[ClientExecutionStep] = []
    metadata: dict = {}

    # Accumulated PTS text (may span multiple pages)
    pts_fragments: list[str] = []
    pts_page_found: bool = False      # have we seen the page-2 PTS row?
    pts_complete: bool = False        # have we collected all PTS continuation?

    with pdfplumber.open(pdf_path) as pdf:
        # Page 1 is always the cover page (Script ID + title graphic only)
        pages = pdf.pages[1:] if len(pdf.pages) > 1 else pdf.pages

        for page in pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 1:
                    continue

                # ── Execution table (always check first) ──────────────────
                if _is_execution_table(table):
                    pts_complete = True  # no more PTS after execution begins
                    execution_steps.extend(_parse_execution_table(table))
                    continue

                # ── Metadata / PTS table (page 2) ─────────────────────────
                if not pts_page_found and _is_metadata_table(table):
                    meta, pts_text = _extract_metadata_and_pts(table)
                    metadata.update({k: v for k, v in meta.items() if v})
                    if pts_text:
                        pts_fragments.append(pts_text)
                    pts_page_found = True
                    # Check if PTS is already complete on this page
                    if pts_text and _PTS_END_SENTINEL.search(pts_text):
                        pts_complete = True
                    continue

                # ── PTS continuation table (pages 3, 4, …) ────────────────
                if pts_page_found and not pts_complete:
                    if _is_pts_continuation_table(table):
                        fragment = _extract_pts_continuation(table)
                        if fragment:
                            pts_fragments.append(fragment)
                            if _PTS_END_SENTINEL.search(fragment):
                                pts_complete = True
                    continue

                # Tables that match nothing (cover Script ID box, signature
                # page, PTS screenshots header) are silently ignored.

    # ── Parse the fully stitched PTS text ─────────────────────────────────
    full_pts = "\n".join(pts_fragments)
    setup_steps.extend(_parse_pts_steps(full_pts))

    return ClientScript(
        setup_steps=_dedup_setup(setup_steps),
        execution_steps=_dedup_exec(execution_steps),
        metadata=metadata,
    )