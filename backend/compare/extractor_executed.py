import pdfplumber
import re
from backend.compare.schemas import (
    SetupStep,
    ExecutedExecutionStep,
    ExecutedScript,
)
from backend.compare.text_parsers import extract_pass_fail, normalize_text


def identify_table_type(table) -> str:
    """Identify if table is execution steps table"""
    if not table or not table[0]:
        return "unknown"
    
    header_row = ' '.join([str(cell or '') for cell in table[0]]).lower()
    
    # Execution table has: Step #, Procedure, Expected Results, Actual Results, Pass/Fail
    if "procedure" in header_row and "expected results" in header_row and "actual results" in header_row:
        return "execution"
    
    return "unknown"


def clean_cell(cell) -> str:
    """Clean and normalize cell content"""
    if cell is None:
        return ""
    
    text = str(cell).strip()
    text = text.replace('\n', ' ')
    text = re.sub(r' +', ' ', text)
    
    return text.strip()


def extract_pre_test_setup(page_text: str) -> list[SetupStep]:
    """Extract Pre-Test Setup steps from text"""
    steps = []
    
    # Find the PTS section
    pts_match = re.search(
        r'Pre-Test Setup \(PTS\)\s+(.+?)(?:PTS Screenshots|Executed Test Script|$)', 
        page_text, 
        re.DOTALL
    )
    
    if not pts_match:
        # Try alternative pattern without (PTS)
        pts_match = re.search(
            r'Pre-Test Setup\s+(.+?)(?:Screenshots|Executed Test Script|$)', 
            page_text, 
            re.DOTALL
        )
    
    if not pts_match:
        return steps
    
    pts_content = pts_match.group(1)
    
    # Pattern to match numbered steps like "1. " or "2. "
    step_pattern = r'(\d+)\.\s+(.+?)(?=\n\d+\.\s+|\Z)'
    
    matches = re.findall(step_pattern, pts_content, re.DOTALL)
    
    for step_num_str, procedure in matches:
        step_num = int(step_num_str)
        # Clean up procedure text
        procedure = re.sub(r'\s+', ' ', procedure).strip()
        
        steps.append(SetupStep(
            step_number=step_num,
            procedure=normalize_text(procedure)
        ))
    
    return steps


def parse_execution_table(table) -> list[ExecutedExecutionStep]:
    """Parse an execution steps table with actual results"""
    steps = []
    
    # Skip header row
    for row in table[1:]:
        if not row or len(row) < 4:
            continue
        
        # Clean cells
        cells = [clean_cell(cell) for cell in row]
        
        # Get non-empty cells with indices
        non_empty_cells = [(idx, cell) for idx, cell in enumerate(cells) if cell]
        
        if not non_empty_cells:
            continue
        
        # Find step number (first digit cell)
        step_num = None
        step_num_idx = None
        
        for idx, cell in non_empty_cells:
            if cell.isdigit():
                step_num = int(cell)
                step_num_idx = idx
                break
        
        if step_num is None:
            continue
        
        # Extract fields
        procedure = ""
        expected_results = ""
        actual_results = ""
        
        remaining_cells = [(idx, cell) for idx, cell in non_empty_cells if idx > step_num_idx]
        
        # Filter out Pass/Fail and timestamps
        content_cells = []
        pass_fail_value = ""
        
        for idx, cell in remaining_cells:
            lower_cell = cell.lower()
            
            # Check if this is a Pass/Fail value
            if lower_cell in ['pass', 'fail', 'n/a']:
                pass_fail_value = cell.upper()
                continue
            
            # Skip timestamp patterns
            if re.match(r'\d{2}-[A-Z]{3}-\d{4}', cell):
                continue
            
            content_cells.append(cell)
        
        # First cell is procedure, second is expected, third is actual
        if len(content_cells) >= 1:
            procedure = content_cells[0]
        if len(content_cells) >= 2:
            expected_results = content_cells[1]
        if len(content_cells) >= 3:
            actual_results = content_cells[2]
        
        # If pass_fail not found in filtering, try robust extraction
        if not pass_fail_value:
            all_cells = [cell for idx, cell in non_empty_cells]
            pass_fail_value = extract_pass_fail(all_cells)
        
        if procedure:
            steps.append(ExecutedExecutionStep(
                step_number=step_num,
                procedure=normalize_text(procedure),
                expected_results=normalize_text(expected_results),
                actual_results=normalize_text(actual_results),
                pass_fail=pass_fail_value
            ))
    
    return steps


def extract_executed_pdf(pdf_path: str) -> ExecutedScript:
    """
    Extract executed (V-Assure) test script PDF.

    - Pre-Test Setup is extracted from numbered text sections
    - Execution steps are extracted from tables with actual results
    - PASS / FAIL is detected robustly from any column
    """

    pre_test_steps: list[SetupStep] = []
    execution_steps: list[ExecutedExecutionStep] = []

    with pdfplumber.open(pdf_path) as pdf:
        # Skip first page (cover), start from page 2
        pages_to_process = pdf.pages[1:] if len(pdf.pages) > 1 else pdf.pages
        
        for page in pages_to_process:
            page_text = page.extract_text() or ""

            # -------------------------------------------------
            # PRE-TEST SETUP (numbered text sections)
            # -------------------------------------------------
            if "Pre-Test Setup" in page_text:
                steps = extract_pre_test_setup(page_text)
                pre_test_steps.extend(steps)

            # -------------------------------------------------
            # EXECUTION TABLES
            # -------------------------------------------------
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                
                if identify_table_type(table) != "execution":
                    continue

                steps = parse_execution_table(table)
                execution_steps.extend(steps)
    
    # Deduplicate and sort
    pre_test_steps = _deduplicate_setup_steps(pre_test_steps)
    execution_steps = _deduplicate_execution_steps(execution_steps)

    return ExecutedScript(
        pre_test_setup=pre_test_steps,
        execution_steps=execution_steps,
    )


def _deduplicate_setup_steps(steps: list[SetupStep]) -> list[SetupStep]:
    """Remove duplicate steps and sort by step number"""
    seen = {}
    for step in steps:
        if step.step_number not in seen:
            seen[step.step_number] = step
    
    return sorted(seen.values(), key=lambda x: x.step_number)


def _deduplicate_execution_steps(steps: list[ExecutedExecutionStep]) -> list[ExecutedExecutionStep]:
    """Remove duplicate execution steps and sort by step number"""
    seen = {}
    for step in steps:
        if step.step_number not in seen:
            seen[step.step_number] = step
    
    return sorted(seen.values(), key=lambda x: x.step_number)