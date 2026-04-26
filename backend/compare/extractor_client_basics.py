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
             The Pre-Test Setup (PTS) cell holds ALL setup steps as a single
             block of text:
               "1. Ensure ...\n   - Role (Security Profile: X)\n2. Ensure ..."
  Page 3+ – Execution table: Step # | Procedure | Expected Results |
                              Actual Results | Pass/Fail
  Last page – Script Pre-Approval signatures (ignored).

Return type: ClientScript  (same schema as before – no downstream changes needed)

Bug fixed: _is_metadata_table previously scanned ALL cells in each row, causing
tables on continuation pages (e.g. page 4 of CLIN-02) to be mis-classified as
metadata when an expected-result cell contained the phrase "pre-test setup"
(e.g. "Study 1 from the pre-test setup is displayed..."). Fix: only inspect
column 0 (the label/key column) when identifying the metadata table.

Ordering fix: _is_execution_table is checked BEFORE _is_metadata_table in the
main loop so a table that matches both heuristics is always treated as execution.
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

# Keywords that must appear together in the header row to classify an
# execution table.  We require at least 2 of the 3 to be present.
EXEC_HEADER_KEYWORDS = {"procedure", "expected results", "pass"}

# Mapping from normalised cell label → metadata field name
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

# Cell values that are never procedure/expected content
_SKIP_VALUES = {
    "pass", "fail", "n/a", "yes", "no",
    "pass / fail / n/a", "pass/fail",
}


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def _clean_cell(cell) -> str:
    """
    Flatten a metadata table cell to a string, preserving internal newlines
    (needed so PTS multi-line text survives into the parser).
    """
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"[ \t]+", " ", text)       # collapse horizontal space
    text = re.sub(r"\n{3,}", "\n\n", text)    # cap consecutive blank lines
    return text.strip()


def _clean_exec_cell(cell) -> str:
    """Flatten an execution-table cell to a single line."""
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Table-type detection
# ---------------------------------------------------------------------------

def _is_execution_table(table) -> bool:
    """
    True when the HEADER ROW (row 0) contains the execution-step column names.
    Requires at least 2 of: 'procedure', 'expected results', 'pass'.
    """
    if not table or not table[0]:
        return False
    header = " ".join(str(c or "").lower() for c in table[0])
    hits = sum(1 for kw in EXEC_HEADER_KEYWORDS if kw in header)
    return hits >= 2


def _is_metadata_table(table) -> bool:
    """
    True when this is the page-2 metadata / Pre-Test Setup table.

    IMPORTANT: Only column 0 (the label column) is inspected.
    Scanning data columns caused false positives on continuation pages when
    an expected-result cell contained "pre-test setup"
    (e.g. "Study 1 from the pre-test setup is displayed in the drop-down").
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


# ---------------------------------------------------------------------------
# Metadata + PTS extraction (page 2 table)
# ---------------------------------------------------------------------------

def _extract_metadata_and_pts(table) -> tuple[dict, str]:
    """
    Parse the page-2 metadata table.

    Layout per row:  [left_key | left_value | right_key | right_value]
    PTS row layout:  [Pre-Test Setup (PTS) | <full PTS text> | '' | '']

    Returns:
        metadata – dict of normalised field names → values
        pts_text – raw (multi-line) Pre-Test Setup cell content
    """
    metadata: dict = {}
    pts_text: str = ""

    for row in table:
        if not row:
            continue

        cells = [_clean_cell(c) for c in row]

        # ---- Pre-Test Setup row (key in col 0, value spans remaining cols) --
        if PTS_KEY_PATTERN.search(cells[0] if cells else ""):
            value_parts = [cells[j] for j in range(1, len(cells)) if cells[j]]
            pts_text = "\n".join(value_parts).strip()
            # Don't break — there may still be metadata on later rows (rare)
            continue

        # ---- Standard key-value pairs (up to two per row) -------------------
        pairs: list[tuple[str, str]] = []
        if len(cells) >= 2:
            pairs.append((cells[0], cells[1]))
        if len(cells) >= 4:
            pairs.append((cells[2], cells[3]))

        for key_raw, value in pairs:
            # Collapse ALL whitespace (handles "V-Assure\nEnvironment")
            key_norm = re.sub(r"\s+", " ", key_raw.lower()).strip().rstrip(":")
            if key_norm in META_KEYS and value:
                metadata[META_KEYS[key_norm]] = value

    return metadata, pts_text


# ---------------------------------------------------------------------------
# Pre-Test Setup parsing
# ---------------------------------------------------------------------------

def _parse_pts_steps(pts_text: str) -> list[SetupStep]:
    """
    Split the PTS block into individual SetupStep objects.

    Input example:
        1. Ensure the following Test Accounts are available ...:
           - Vault Admin (Security Profile: Vault Admin)
           - TMF Manager (Security Profile: TMF Manager)
        2. Ensure the following Studies are available ...

    Each top-level numbered item becomes one SetupStep.  Bullet sub-items are
    preserved as multi-line procedure text so the existing comparator role-
    extraction logic continues to work unchanged.
    """
    if not pts_text:
        return []

    steps: list[SetupStep] = []

    # Split on "N." at the start of a line, keeping the delimiter with its chunk
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

        # Clean each line individually, preserve structure
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
    """
    Parse Step # | Procedure | Expected Results | Actual Results | Pass/Fail.

    Column positions are detected from the header row for robustness.
    The Actual Results and Pass/Fail columns are blank in client templates.
    """
    steps: list[ClientExecutionStep] = []

    if not table or not table[0]:
        return steps

    # Detect column positions from header
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

        # Step number: first cell whose content is a plain integer
        step_num: int | None = None
        step_idx: int | None = None
        for i, c in non_empty:
            if c.isdigit():
                step_num = int(c)
                step_idx = i
                break

        if step_num is None:
            continue

        # Extract by detected column positions
        procedure = ""
        expected_results = ""

        if procedure_col is not None and procedure_col < len(cells):
            procedure = cells[procedure_col]
        if expected_col is not None and expected_col < len(cells):
            expected_results = cells[expected_col]

        # Positional fallback (guards against unexpected column layouts)
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

    with pdfplumber.open(pdf_path) as pdf:
        # Page 1 is always the cover page (Script ID + title graphic only)
        pages = pdf.pages[1:] if len(pdf.pages) > 1 else pdf.pages

        for page in pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2:
                    continue

                # IMPORTANT: check execution BEFORE metadata.
                # A continuation-page execution table (e.g. page 4 of CLIN-02)
                # would otherwise be mis-classified as metadata because
                # _is_metadata_table is too permissive without this ordering.
                if _is_execution_table(table):
                    execution_steps.extend(_parse_execution_table(table))

                elif _is_metadata_table(table):
                    meta, pts_text = _extract_metadata_and_pts(table)
                    metadata.update({k: v for k, v in meta.items() if v})
                    setup_steps.extend(_parse_pts_steps(pts_text))

                # Tables that match neither (cover Script ID box, signature
                # page) are silently ignored.

    return ClientScript(
        setup_steps=_dedup_setup(setup_steps),
        execution_steps=_dedup_exec(execution_steps),
        metadata=metadata,
    )