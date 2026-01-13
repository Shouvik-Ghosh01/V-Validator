import pdfplumber
from backend.compare.schemas import (
    SetupStep,
    ExecutedExecutionStep,
    ExecutedScript,
)
from backend.compare.table_detection import identify_table_type
from backend.compare.text_parsers import extract_pass_fail, normalize_text
import re


def extract_executed_pdf(pdf_path: str) -> ExecutedScript:
    """
    Extract executed (V-Assure) test script PDF.

    - Pre-Test Setup is extracted from bullet text
    - Execution steps are extracted from tables
    - PASS / FAIL is detected robustly from any column
    """

    pre_test_steps: list[SetupStep] = []
    execution_steps: list[ExecutionStep] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""

            # -------------------------------------------------
            # PRE-TEST SETUP (bullets or numbered text)
            # -------------------------------------------------
            if "Pre-Test Setup" in page_text:
                for line in page_text.splitlines():
                    line = line.strip()

                    # Match bullets: "-", "•", or numbered "1. ..."
                    if re.match(r"^[-•]\s+", line) or re.match(r"^\d+\.\s+", line):
                        cleaned = re.sub(r"^[-•]\s+|\d+\.\s+", "", line)

                        pre_test_steps.append(
                            SetupStep(
                                step_number=len(pre_test_steps) + 1,
                                procedure=normalize_text(cleaned),
                            )
                        )

            # -------------------------------------------------
            # EXECUTION TABLES
            # -------------------------------------------------
            tables = page.extract_tables()
            for table in tables:
                if identify_table_type(table) != "execution":
                    continue

                # Skip header row
                for row in table[1:]:
                    if not row or len(row) < 3:
                        continue

                    cells = [normalize_text(c) for c in row if c]

                    # Step number must exist
                    if not cells or not cells[0].isdigit():
                        continue

                    step_number = int(cells[0])

                    # Safe field extraction
                    procedure = cells[1] if len(cells) > 1 else ""
                    expected_results = cells[2] if len(cells) > 2 else ""
                    actual_results = cells[3] if len(cells) > 3 else ""

                    # 🔑 Robust PASS / FAIL detection
                    pass_fail = extract_pass_fail(cells)

                    execution_steps.append(                        
                        ExecutedExecutionStep(
                            step_number=step_number,
                            procedure=procedure,
                            expected_results=expected_results,
                            actual_results=actual_results,
                            pass_fail=pass_fail,
                        )
                    )

    return ExecutedScript(
        pre_test_setup=pre_test_steps,
        execution_steps=execution_steps,
    )