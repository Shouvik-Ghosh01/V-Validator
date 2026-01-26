import pdfplumber
import re
from backend.compare.schemas import (
    SetupStep,
    ClientExecutionStep,
    ClientScript,
)
from backend.compare.text_parsers import normalize_text


def extract_metadata(first_page) -> dict:
    """Extract metadata from first page of client PDF"""
    text = first_page.extract_text()
    
    # Extract Script ID
    script_id_match = re.search(r'Test Script ID\s+([A-Z0-9\-]+)', text)
    script_id = script_id_match.group(1) if script_id_match else ""
    
    # Extract Title
    title_match = re.search(r'Title\s+(.+?)(?:\n|Description)', text)
    title = title_match.group(1).strip() if title_match else ""
    
    # Extract Description
    desc_match = re.search(r'Description\s+(.+?)(?:\n|Run Number|Setup Steps)', text, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ""
    description = re.sub(r'\s+', ' ', description)  # Normalize whitespace
    
    # Extract Run Number
    run_match = re.search(r'Run Number\s+(\d+)', text)
    run_number = run_match.group(1) if run_match else ""
    
    return {
        "script_id": script_id,
        "title": title,
        "description": description,
        "run_number": run_number
    }


def identify_table_type(table) -> str:
    """
    Identify if table is setup or execution based on headers
    Returns: 'setup', 'execution', or 'unknown'
    """
    if not table or not table[0]:
        return "unknown"
    
    # Get first row (headers) and join, convert to lowercase
    header_row = ' '.join([str(cell or '') for cell in table[0]]).lower()
    
    # Check for execution table indicators first (more specific)
    if "expected results" in header_row:
        return "execution"
    
    # Check for setup table indicators
    if ("actual results" in header_row or "actual result" in header_row) and \
       ("complete" in header_row):
        return "setup"
    
    # Alternative setup pattern: just "procedure" and "complete"
    if "procedure" in header_row and "complete" in header_row:
        if "expected" not in header_row:
            return "setup"
    
    return "unknown"


def clean_cell(cell) -> str:
    """Clean and normalize cell content - converts to single line"""
    if cell is None:
        return ""
    
    text = str(cell).strip()
    text = text.replace('\n', ' ')
    text = re.sub(r' +', ' ', text)
    
    return text.strip()


def parse_setup_table(table) -> list:
    """Parse a setup steps table"""
    steps = []
    
    # Skip header row
    for row in table[1:]:
        if not row or len(row) < 2:
            continue
        
        # Clean cells
        cells = [clean_cell(cell) for cell in row]
        
        # Filter out empty cells
        non_empty_cells = [(idx, cell) for idx, cell in enumerate(cells) if cell]
        
        if not non_empty_cells:
            continue
        
        # Try to find step number (usually first non-empty cell that's a digit)
        step_num = None
        step_num_idx = None
        
        for idx, cell in non_empty_cells:
            if cell.isdigit():
                step_num = int(cell)
                step_num_idx = idx
                break
        
        if step_num is None:
            continue
        
        # Procedure is typically the next non-empty cell after step number
        procedure = ""
        for idx, cell in non_empty_cells:
            if idx > step_num_idx:
                # Get the first substantive cell after step number
                # Skip cells that are just "No", "Yes", checkmarks, etc.
                if cell.lower() not in ['no', 'yes', 'n/a', '✓', 'x']:
                    procedure = cell
                    break
        
        # Only add if we have a valid procedure
        if procedure:
            steps.append(SetupStep(
                step_number=step_num,
                procedure=normalize_text(procedure)
            ))
    
    return steps


def parse_execution_table(table) -> list:
    """Parse an execution steps table"""
    steps = []
    
    # Skip header row
    for row in table[1:]:
        if not row or len(row) < 3:
            continue
        
        # Clean cells
        cells = [clean_cell(cell) for cell in row]
        
        # Filter out empty cells but keep track of indices
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
        
        # Extract procedure and expected results from remaining cells
        procedure = ""
        expected_results = ""
        
        remaining_cells = [(idx, cell) for idx, cell in non_empty_cells if idx > step_num_idx]
        
        # Filter out status cells (Pass/Fail/N/A, Yes/No, etc.)
        content_cells = [
            cell for idx, cell in remaining_cells 
            if cell.lower() not in ['pass', 'fail', 'n/a', 'yes', 'no', '✓', 'x', 'pass / fail / n/a']
        ]
        
        # First content cell is procedure, second is expected results
        if len(content_cells) >= 1:
            procedure = content_cells[0]
        if len(content_cells) >= 2:
            expected_results = content_cells[1]
        
        # Only add if we have at least a procedure
        if procedure:
            steps.append(ClientExecutionStep(
                step_number=step_num,
                procedure=normalize_text(procedure),
                expected_results=normalize_text(expected_results)
            ))
    
    return steps


def _deduplicate_setup_steps(steps: list) -> list:
    """Remove duplicate steps and sort by step number"""
    seen = {}
    for step in steps:
        if step.step_number not in seen:
            seen[step.step_number] = step
    
    return sorted(seen.values(), key=lambda x: x.step_number)


def _deduplicate_execution_steps(steps: list) -> list:
    """Remove duplicate execution steps and sort by step number"""
    seen = {}
    for step in steps:
        if step.step_number not in seen:
            seen[step.step_number] = step
    
    return sorted(seen.values(), key=lambda x: x.step_number)


def extract_client_pdf(pdf_path: str) -> ClientScript:
    """
    Extract client (template) test script PDF
    Uses robust table detection and cell parsing
    """
    setup_steps = []
    execution_steps = []
    metadata = {}

    with pdfplumber.open(pdf_path) as pdf:
        # Extract metadata from first page
        if pdf.pages:
            try:
                metadata = extract_metadata(pdf.pages[0])
            except Exception as e:
                print(f"Warning: Could not extract metadata: {e}")
                metadata = {}
        
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                if not table or len(table) < 2:
                    continue
                
                table_type = identify_table_type(table)

                # -------- SETUP --------
                if table_type == "setup":
                    steps = parse_setup_table(table)
                    setup_steps.extend(steps)

                # -------- EXECUTION --------
                elif table_type == "execution":
                    steps = parse_execution_table(table)
                    execution_steps.extend(steps)
    
    # Sort and deduplicate steps
    setup_steps = _deduplicate_setup_steps(setup_steps)
    execution_steps = _deduplicate_execution_steps(execution_steps)

    return ClientScript(setup_steps, execution_steps, metadata)