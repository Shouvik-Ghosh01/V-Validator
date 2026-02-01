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
    """
    Preserve line breaks, bullets, spacing.
    Used ONLY for setup steps.
    """
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def normalize_flat(text: str) -> str:
    """
    Flatten text into a single line.
    Used ONLY for execution steps.
    """
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =====================================================
# METADATA EXTRACTION
# =====================================================
def extract_metadata(page) -> dict:
    text = remove_pdf_noise(page.extract_text() or "")

    script_id = re.search(r"Test Script ID\s+([A-Z0-9\-]+)", text)
    title = re.search(r"Title\s+(.+?)(?:\n|Description)", text)
    desc = re.search(r"Description\s+(.+?)(?:\n|Build Number|Start Time)", text, re.DOTALL)
    start = re.search(r"Start Time\s+(.+?)(?:\n|End Time)", text)
    end = re.search(r"End Time\s+(.+?)(?:\n|Pre-Test)", text)

    description = normalize_preserve_structure(desc.group(1)) if desc else ""

    return {
        "script_id": script_id.group(1) if script_id else "",
        "title": title.group(1).strip() if title else "",
        "description": description,
        "start_time": start.group(1).strip() if start else "",
        "end_time": end.group(1).strip() if end else "",
        "script_run_time": calculate_runtime(
            start.group(1) if start else "",
            end.group(1) if end else "",
        ),
    }


def calculate_runtime(start_time: str, end_time: str) -> str:
    try:
        start_dt = datetime.strptime(start_time.split(" GMT")[0], "%d-%b-%Y %H:%M:%S")
        end_dt = datetime.strptime(end_time.split(" GMT")[0], "%d-%b-%Y %H:%M:%S")
        diff = end_dt - start_dt
        total = int(diff.total_seconds())
        return f"{total//3600:02d}:{(total%3600)//60:02d}:{total%60:02d}"
    except Exception:
        return "00:00:00"


# =====================================================
# PRE-TEST SETUP EXTRACTION
# =====================================================
def extract_pre_test_setup(page_text: str) -> list:
    steps = []

    page_text = remove_pdf_noise(page_text)

    match = re.search(
        r"Pre-Test Setup(?: \(PTS\))?\s+(.+?)(?:Executed Test Script|Screenshots|$)",
        page_text,
        re.DOTALL,
    )

    if not match:
        return steps

    content = match.group(1)

    step_pattern = r"(\d+)\.\s+(.+?)(?=\n\d+\.\s+|\Z)"
    matches = re.findall(step_pattern, content, re.DOTALL)

    for step_num, procedure in matches:
        cleaned = normalize_preserve_structure(procedure)
        steps.append(
            SetupStep(
                step_number=int(step_num),
                procedure=cleaned,
            )
        )

    return steps


# =====================================================
# EXECUTION TABLE HANDLING
# =====================================================
def identify_table_type(table) -> str:
    if not table or not table[0]:
        return "unknown"

    header = " ".join(str(c or "") for c in table[0]).lower()
    if "procedure" in header and "expected results" in header and "actual results" in header:
        return "execution"

    return "unknown"


def clean_cell(cell) -> str:
    if cell is None:
        return ""
    return normalize_flat(str(cell))


def parse_execution_table(table) -> list:
    steps = []

    for row in table[1:]:
        if not row or len(row) < 4:
            continue

        cells = [clean_cell(c) for c in row]
        non_empty = [(i, c) for i, c in enumerate(cells) if c]

        step_num = None
        step_idx = None

        for idx, cell in non_empty:
            if cell.isdigit():
                step_num = int(cell)
                step_idx = idx
                break

        if step_num is None:
            continue

        procedure = expected = actual = ""
        pass_fail = ""

        for idx, cell in non_empty:
            low = cell.lower()
            if low in ("pass", "fail", "n/a"):
                pass_fail = cell.upper()
            elif idx > step_idx:
                if not procedure:
                    procedure = cell
                elif not expected:
                    expected = cell
                elif not actual:
                    actual = cell

        if not pass_fail:
            pass_fail = extract_pass_fail([c for _, c in non_empty])

        steps.append(
            ExecutedExecutionStep(
                step_number=step_num,
                procedure=procedure,
                expected_results=expected,
                actual_results=actual,
                pass_fail=pass_fail,
            )
        )

    return steps


# =====================================================
# DEDUPLICATION
# =====================================================
def dedupe_steps(steps: list) -> list:
    seen = {}
    for s in steps:
        if s.step_number not in seen:
            seen[s.step_number] = s
    return sorted(seen.values(), key=lambda x: x.step_number)


# =====================================================
# MAIN ENTRY
# =====================================================
def extract_executed_pdf(pdf_path: str) -> ExecutedScript:
    pre_test_steps = []
    execution_steps = []
    metadata = {}

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[1:] if len(pdf.pages) > 1 else pdf.pages

        if pages:
            metadata = extract_metadata(pages[0])

        for page in pages:
            text = remove_pdf_noise(page.extract_text() or "")

            if "Pre-Test Setup" in text:
                pre_test_steps.extend(extract_pre_test_setup(text))

            for table in page.extract_tables() or []:
                if identify_table_type(table) == "execution":
                    execution_steps.extend(parse_execution_table(table))

    return ExecutedScript(
        pre_test_setup=dedupe_steps(pre_test_steps),
        execution_steps=dedupe_steps(execution_steps),
        metadata=metadata,
    )