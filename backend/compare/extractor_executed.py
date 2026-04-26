import pdfplumber
import re
from datetime import datetime
from backend.compare.schemas import (
    SetupStep,
    ExecutedExecutionStep,
    ExecutedScript,
)
from backend.compare.text_parsers import extract_pass_fail

# =====================================================
# CONSTANTS
# =====================================================
EXEC_HEADER_KEYWORDS = {"procedure", "expected results", "actual results"}

META_KEYS = {
    "test script id":       "script_id",
    "title":                "title",
    "description":          "description",
    "build number":         "build_number",
    "vault name":           "vault_name",
    "product version":      "product_version",
    "v-assure environment": "v_assure_environment",
    "run number":           "run_number",
    "start time":           "start_time",
    "end time":             "end_time",
}

PTS_KEY_PATTERN = re.compile(r"pre.?test\s+setup", re.IGNORECASE)

_SKIP_VALUES = {"pass", "fail", "n/a", "yes", "no", "pass / fail / n/a", "pass/fail"}

# Sentinel marking the final line of PTS content across all pages
_PTS_END_SENTINEL = re.compile(
    r"all active content plan items have a green harvey ball",
    re.IGNORECASE,
)

# =====================================================
# PDF NOISE REMOVAL
# =====================================================
FOOTER_PATTERNS = [
    r"Veeva Systems Confidential.*",
    r"Page\s+\d+\s+of\s+\d+",
]


def remove_pdf_noise(text: str) -> str:
    if not text:
        return ""
    for pattern in FOOTER_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text.strip()


# =====================================================
# TEXT NORMALIZATION
# =====================================================
def normalize_preserve_structure(text: str) -> str:
    """Preserve line breaks and bullets. Used for setup steps."""
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def normalize_flat(text: str) -> str:
    """Flatten to single line. Used for execution steps."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# =====================================================
# CELL HELPERS
# =====================================================
def _clean_cell(cell) -> str:
    """Preserve internal newlines — needed for multi-line metadata cells."""
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_exec_cell(cell) -> str:
    """Flatten execution table cell to a single line."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", str(cell).strip()).strip()


# =====================================================
# TABLE TYPE DETECTION
# =====================================================
def _is_execution_table(table) -> bool:
    """True when header row contains execution column keywords."""
    if not table or not table[0]:
        return False
    header = " ".join(str(c or "").lower() for c in table[0])
    hits = sum(1 for kw in EXEC_HEADER_KEYWORDS if kw in header)
    return hits >= 2


def _is_metadata_table(table) -> bool:
    """
    True when this is the page-2 metadata / PTS table.
    Only col 0 is inspected to avoid false positives.
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
    cell as a standalone table: single data row, empty col 0, text in col 1.
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


# =====================================================
# METADATA EXTRACTION  (table-based — reliable)
# =====================================================
def _extract_metadata_from_table(table) -> tuple[dict, str]:
    """
    Parse the page-2 metadata table.
    Layout per row: [left_key | left_value | right_key | right_value]
    PTS row:        [Pre-Test Setup (PTS) | <full PTS text> | '' | '']

    Returns (metadata_dict, pts_text_fragment).
    """
    metadata: dict = {}
    pts_text: str = ""

    for row in table:
        if not row:
            continue
        cells = [_clean_cell(c) for c in row]

        # PTS row — key is in col 0, value spans remaining cols
        if PTS_KEY_PATTERN.search(cells[0] if cells else ""):
            value_parts = [cells[j] for j in range(1, len(cells)) if cells[j]]
            pts_text = "\n".join(value_parts).strip()
            continue

        # Standard two key-value pairs per row
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
    """Pull PTS overflow text from a cross-page continuation table."""
    for row in table:
        if not row or len(row) < 2:
            continue
        col0 = str(row[0] or "").strip()
        col1 = str(row[1] or "").strip()
        if col0 == "" and len(col1) > 30:
            return col1
    return ""


# =====================================================
# RUNTIME CALCULATION
# =====================================================
def calculate_runtime(start_time: str, end_time: str) -> str:
    try:
        fmt = "%d-%b-%Y %H:%M:%S"
        start_dt = datetime.strptime(start_time.split(" GMT")[0].strip(), fmt)
        end_dt   = datetime.strptime(end_time.split(" GMT")[0].strip(), fmt)
        total = int((end_dt - start_dt).total_seconds())
        return f"{total//3600:02d}:{(total%3600)//60:02d}:{total%60:02d}"
    except Exception:
        return "00:00:00"


# =====================================================
# PRE-TEST SETUP PARSING
# =====================================================
def _parse_pts_steps(pts_text: str) -> list[SetupStep]:
    """
    Split the fully-stitched PTS text into individual SetupStep objects.
    Each top-level numbered item (N.) becomes one step. Bullet sub-lines
    are preserved so downstream role/value extraction keeps working.
    """
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


# =====================================================
# EXECUTION TABLE PARSING
# =====================================================
def _parse_execution_table(table) -> list[ExecutedExecutionStep]:
    steps: list[ExecutedExecutionStep] = []

    if not table or not table[0]:
        return steps

    # Detect column positions from header
    header = [str(c or "").strip().lower() for c in table[0]]
    procedure_col: int | None = None
    expected_col:  int | None = None
    actual_col:    int | None = None

    for idx, h in enumerate(header):
        if "procedure"        in h and procedure_col is None: procedure_col = idx
        if "expected"         in h and expected_col  is None: expected_col  = idx
        if "actual"           in h and actual_col    is None: actual_col    = idx

    for row in table[1:]:
        if not row or len(row) < 4:
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

        procedure = expected = actual = ""
        pass_fail = ""

        # Extract by detected column positions
        if procedure_col is not None and procedure_col < len(cells):
            procedure = cells[procedure_col]
        if expected_col is not None and expected_col < len(cells):
            expected = cells[expected_col]
        if actual_col is not None and actual_col < len(cells):
            actual = cells[actual_col]

        # Pass/fail: look for explicit keyword, else use helper
        for _, cell in non_empty:
            if cell.upper() in ("PASS", "FAIL", "N/A"):
                pass_fail = cell.upper()
                break

        if not pass_fail:
            pass_fail = extract_pass_fail([c for _, c in non_empty])

        # Positional fallback if column detection missed procedure
        if not procedure:
            content = [
                c for i, c in non_empty
                if i > (step_idx or 0) and c.lower() not in _SKIP_VALUES
            ]
            if content:     procedure = content[0]
            if len(content) >= 2: expected  = content[1]
            if len(content) >= 3: actual    = content[2]

        if procedure:
            steps.append(ExecutedExecutionStep(
                step_number=step_num,
                procedure=procedure,
                expected_results=expected,
                actual_results=actual,
                pass_fail=pass_fail,
            ))

    return steps


# =====================================================
# DEDUPLICATION
# =====================================================
def _dedup(steps: list) -> list:
    seen: dict = {}
    for s in steps:
        if s.step_number not in seen:
            seen[s.step_number] = s
    return sorted(seen.values(), key=lambda x: x.step_number)


# =====================================================
# MAIN ENTRY
# =====================================================
def extract_executed_pdf(pdf_path: str) -> ExecutedScript:
    """
    Extract a Veeva Basics Executed Test Script PDF.

    Key behaviours
    ──────────────
    • Metadata is extracted from the page-2 table (not raw text) so that
      the two-column layout (e.g. Title / Build Number on one row) is
      handled correctly.

    • PTS text is stitched across pages 2–4:
        - Page 2 table col-1 of the PTS row  → steps 1–3 (truncated)
        - Pages 3 & 4: continuation tables (empty col-0, text in col-1)
          → remainder of steps 4–6
      All fragments are joined before step parsing so that dynamic
      executed values (usernames, app names, document numbers) are
      preserved in full.

    • Execution tables are detected by header keywords and parsed by
      column position, with a positional fallback for robustness.
    """
    setup_steps:     list[SetupStep]             = []
    execution_steps: list[ExecutedExecutionStep] = []
    metadata:        dict                        = {}

    pts_fragments:   list[str] = []
    pts_page_found:  bool      = False   # have we seen the page-2 PTS row?
    pts_complete:    bool      = False   # have we collected all PTS pages?

    with pdfplumber.open(pdf_path) as pdf:
        # Page 1 is always the cover page — skip it
        pages = pdf.pages[1:] if len(pdf.pages) > 1 else pdf.pages

        for page in pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 1:
                    continue

                # ── Execution table (always check first) ──────────────
                if _is_execution_table(table):
                    pts_complete = True
                    execution_steps.extend(_parse_execution_table(table))
                    continue

                # ── Metadata / PTS table (page 2) ─────────────────────
                if not pts_page_found and _is_metadata_table(table):
                    meta, pts_text = _extract_metadata_from_table(table)
                    metadata.update({k: v for k, v in meta.items() if v})
                    if pts_text:
                        pts_fragments.append(pts_text)
                    pts_page_found = True
                    if pts_text and _PTS_END_SENTINEL.search(pts_text):
                        pts_complete = True
                    continue

                # ── PTS continuation tables (pages 3, 4, …) ───────────
                if pts_page_found and not pts_complete:
                    if _is_pts_continuation_table(table):
                        fragment = _extract_pts_continuation(table)
                        if fragment:
                            pts_fragments.append(fragment)
                            if _PTS_END_SENTINEL.search(fragment):
                                pts_complete = True
                    continue

                # All other tables (script-ID header, screenshot headers,
                # signature page) are silently ignored.

    # Add runtime to metadata
    metadata["script_run_time"] = calculate_runtime(
        metadata.get("start_time", ""),
        metadata.get("end_time", ""),
    )

    # Parse the fully stitched PTS text
    full_pts = "\n".join(pts_fragments)
    setup_steps.extend(_parse_pts_steps(full_pts))

    return ExecutedScript(
        pre_test_setup=_dedup(setup_steps),
        execution_steps=_dedup(execution_steps),
        metadata=metadata,
    )