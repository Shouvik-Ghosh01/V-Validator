"""
Test Script PDF Extractor - Table-Based Version
Extracts structured data from test script PDFs using table detection
Modified to auto-name output files based on Script ID
"""

import pdfplumber
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import os


@dataclass
class SetupStep:
    """Structure for Setup Steps"""
    step_number: int
    procedure: str


@dataclass
class ExecutionStep:
    """Structure for Execution Steps"""
    step_number: int
    procedure: str
    expected_results: str


@dataclass
class TestScriptMetadata:
    """Test script header metadata"""
    script_id: str
    title: str
    description: str
    run_number: str


@dataclass
class TestScriptData:
    """Complete test script structure"""
    metadata: TestScriptMetadata
    setup_steps: List[SetupStep]
    execution_steps: List[ExecutionStep]
    extraction_timestamp: str
    source_file: str
    
    # Statistics
    total_setup_steps: int
    total_execution_steps: int
    total_pages: int
    

class TableBasedExtractor:
    """Extract structured data from test script PDFs using table detection"""
    
    def __init__(self, debug=False):
        self.debug = debug
        self.log_messages = []
        
    def log(self, message: str):
        """Internal logging that doesn't print"""
        self.log_messages.append(message)
        if self.debug:
            print(message)
        
    def extract_from_pdf(self, pdf_path: str) -> TestScriptData:
        """
        Main extraction method using table detection
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            TestScriptData object with all extracted information
        """
        with pdfplumber.open(pdf_path) as pdf:
            # Extract metadata from first page
            metadata = self._extract_metadata(pdf.pages[0])
            
            # Track current section
            setup_steps = []
            execution_steps = []
            
            # Process each page
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                
                # Extract tables from current page
                tables = page.extract_tables()
                
                # self.log(f"Page {page_num}: Found {len(tables)} tables")
                
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    
                    # Identify table type by headers
                    table_type = self._identify_table_type(table)
                    
                    # self.log(f"  Table {table_idx + 1}: Type = {table_type}")
                    
                    # Process based on table type (not section flags)
                    if table_type == "setup":
                        steps = self._parse_setup_table(table, page_num)
                        setup_steps.extend(steps)
                        # self.log(f"    Extracted {len(steps)} setup steps from this table")
                        
                    elif table_type == "execution":
                        steps = self._parse_execution_table(table, page_num)
                        execution_steps.extend(steps)
                        # self.log(f"    Extracted {len(steps)} execution steps from this table")
            
            # Sort steps by step number
            setup_steps.sort(key=lambda x: x.step_number)
            execution_steps.sort(key=lambda x: x.step_number)
            
            return TestScriptData(
                metadata=metadata,
                setup_steps=setup_steps,
                execution_steps=execution_steps,
                extraction_timestamp=datetime.now().isoformat(),
                source_file=pdf_path,
                total_setup_steps=len(setup_steps),
                total_execution_steps=len(execution_steps),
                total_pages=len(pdf.pages)
            )
    
    def _extract_metadata(self, first_page) -> TestScriptMetadata:
        """Extract header metadata from first page"""
        text = first_page.extract_text()
        
        # Extract Script ID
        script_id_match = re.search(r'Test Script ID\s+([A-Z0-9\-]+)', text)
        script_id = script_id_match.group(1) if script_id_match else ""
        
        # Extract Title
        title_match = re.search(r'Title\s+(.+?)(?:\n|Description)', text)
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract Description
        desc_match = re.search(r'Description\s+(.+?)(?:\n|Run Number)', text, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""
        description = re.sub(r'\s+', ' ', description)  # Normalize whitespace
        
        # Extract Run Number
        run_match = re.search(r'Run Number\s+(\d+)', text)
        run_number = run_match.group(1) if run_match else ""
        
        return TestScriptMetadata(
            script_id=script_id,
            title=title,
            description=description,
            run_number=run_number
        )
    
    def _identify_table_type(self, table: List[List[str]]) -> str:
        """
        Identify if table is setup or execution based on headers
        
        Returns: 'setup', 'execution', or 'unknown'
        """
        if not table or not table[0]:
            return "unknown"
        
        # Get first row (headers) and join, convert to lowercase
        header_row = ' '.join([str(cell or '') for cell in table[0]]).lower()
        
        # Check for execution table indicators first (more specific)
        # Execution has: Step, Procedure, Expected Results, Actual Results, Pass/Fail
        if "expected results" in header_row:
            return "execution"
        
        # Check for setup table indicators
        # Setup has: Step, Procedure, Actual Results, Complete?
        # Key: has "actual results" and "complete" but NO "expected results"
        if ("actual results" in header_row or "actual result" in header_row) and \
           ("complete" in header_row):
            return "setup"
        
        # Alternative setup pattern: just "procedure" and "complete"
        if "procedure" in header_row and "complete" in header_row:
            if "expected" not in header_row:
                return "setup"
        
        return "unknown"
    
    def _parse_setup_table(self, table: List[List[str]], page_num: int) -> List[SetupStep]:
        """Parse a setup steps table"""
        steps = []
        
        # Skip header row
        for row_idx, row in enumerate(table[1:], 1):
            if not row or len(row) < 2:
                continue
            
            # Clean cells
            cells = [self._clean_cell(cell) for cell in row]
            
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
                    procedure=procedure
                ))
        
        return steps
    
    def _parse_execution_table(self, table: List[List[str]], page_num: int) -> List[ExecutionStep]:
        """Parse an execution steps table"""
        steps = []
        
        # Skip header row
        for row_idx, row in enumerate(table[1:], 1):
            if not row or len(row) < 3:
                continue
            
            # Clean cells
            cells = [self._clean_cell(cell) for cell in row]
            
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
                steps.append(ExecutionStep(
                    step_number=step_num,
                    procedure=procedure,
                    expected_results=expected_results
                ))
        
        return steps
    
    def _clean_cell(self, cell, preserve_empty_lines: bool = False) -> str:
        """
        Clean and normalize cell content - converts to single line
        
        Args:
            cell: Cell content from PDF table
            preserve_empty_lines: Not used in this version
        """
        if cell is None:
            return ""
        
        text = str(cell).strip()
        
        # Replace all newlines with spaces
        text = text.replace('\n', ' ')
        
        # Normalize multiple spaces to single space
        text = re.sub(r' +', ' ', text)
        
        return text.strip()
    
    def _sanitize_filename(self, script_id: str) -> str:
        """
        Sanitize script ID to create a valid filename
        
        Args:
            script_id: The script ID to sanitize
            
        Returns:
            Safe filename string
        """
        # Replace any characters that aren't alphanumeric, dash, or underscore
        safe_name = re.sub(r'[^\w\-]', '_', script_id)
        # Remove multiple consecutive underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        
        return safe_name if safe_name else "unknown_script"
    
    def export_to_json(self, data: TestScriptData, output_path: str = None):
        """
        Export extracted data to JSON (auto-named by script ID if no path provided)
        
        Args:
            data: TestScriptData object
            output_path: Optional path to save JSON file. If None, auto-generates from script ID
        """
        # Auto-generate filename from script ID if not provided
        if output_path is None:
            safe_script_id = self._sanitize_filename(data.metadata.script_id)
            output_path = f"{safe_script_id}.json"
        
        data_dict = {
            'metadata': asdict(data.metadata),
            'setup_steps': [asdict(step) for step in data.setup_steps],
            'execution_steps': [asdict(step) for step in data.execution_steps],
            'extraction_timestamp': data.extraction_timestamp,
            'source_file': data.source_file,
            'stats': {
                'total_setup_steps': data.total_setup_steps,
                'total_execution_steps': data.total_execution_steps,
                'total_pages': data.total_pages
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Exported JSON: {output_path}")
        return output_path
    
    def validate_extraction(self, data: TestScriptData) -> Dict[str, any]:
        """Validate the extracted data for completeness"""
        issues = []
        warnings = []
        
        # Check metadata
        if not data.metadata.script_id:
            issues.append("Missing Script ID")
        if not data.metadata.title:
            warnings.append("Missing Title")
        
        # Check steps
        if data.total_setup_steps == 0:
            warnings.append("No setup steps found")
        if data.total_execution_steps == 0:
            issues.append("No execution steps found")
        
        # Check for gaps in step numbering
        setup_nums = [s.step_number for s in data.setup_steps]
        if setup_nums:
            expected = list(range(1, max(setup_nums) + 1))
            if setup_nums != expected:
                missing = set(expected) - set(setup_nums)
                warnings.append(f"Gap in setup step numbering: missing {missing}")
        
        exec_nums = [s.step_number for s in data.execution_steps]
        if exec_nums:
            expected = list(range(1, max(exec_nums) + 1))
            if exec_nums != expected:
                missing = set(expected) - set(exec_nums)
                warnings.append(f"Gap in execution step numbering: missing {missing}")
        
        # Check for duplicate step numbers
        if len(setup_nums) != len(set(setup_nums)):
            warnings.append("Duplicate setup step numbers found")
        if len(exec_nums) != len(set(exec_nums)):
            warnings.append("Duplicate execution step numbers found")
        
        # Check for empty procedures
        empty_setup_procs = sum(1 for s in data.setup_steps if not s.procedure.strip())
        empty_exec_procs = sum(1 for s in data.execution_steps if not s.procedure.strip())
        
        if empty_setup_procs > 0:
            warnings.append(f"{empty_setup_procs} setup steps have empty procedures")
        if empty_exec_procs > 0:
            warnings.append(f"{empty_exec_procs} execution steps have empty procedures")
        
        # Check for empty expected results in execution steps
        empty_expected = sum(1 for s in data.execution_steps if not s.expected_results.strip())
        if empty_expected > 0:
            warnings.append(f"{empty_expected} execution steps have empty expected results")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'stats': {
                'setup_steps': data.total_setup_steps,
                'execution_steps': data.total_execution_steps,
                'pages_processed': data.total_pages
            }
        }
    
    def generate_extraction_report(self, data: TestScriptData, validation: Dict) -> str:
        """Generate a human-readable extraction report"""
        report = []
        report.append("=" * 60)
        report.append("TEST SCRIPT EXTRACTION REPORT")
        report.append("=" * 60)
        report.append(f"\nScript ID: {data.metadata.script_id}")
        report.append(f"Title: {data.metadata.title}")
        report.append(f"Description: {data.metadata.description}")
        report.append(f"Run Number: {data.metadata.run_number}")
        report.append(f"\nSource File: {data.source_file}")
        report.append(f"Extracted: {data.extraction_timestamp}")
        report.append(f"Total Pages: {data.total_pages}")
        
        report.append("\n" + "-" * 60)
        report.append("EXTRACTION STATISTICS")
        report.append("-" * 60)
        report.append(f"Setup Steps: {data.total_setup_steps}")
        report.append(f"Execution Steps: {data.total_execution_steps}")
        
        report.append("\n" + "-" * 60)
        report.append("VALIDATION RESULTS")
        report.append("-" * 60)
        report.append(f"Status: {'✓ VALID' if validation['valid'] else '✗ INVALID'}")
        
        if validation['issues']:
            report.append("\nISSUES (Critical):")
            for issue in validation['issues']:
                report.append(f"  ✗ {issue}")
        
        if validation['warnings']:
            report.append("\nWARNINGS:")
            for warning in validation['warnings']:
                report.append(f"  ⚠ {warning}")
        
        if not validation['issues'] and not validation['warnings']:
            report.append("  No issues found!")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


# Example usage
if __name__ == "__main__":
    # Initialize extractor with DEBUG enabled
    extractor = TableBasedExtractor(debug=True)
    
    # Extract from PDF
    pdf_path = "Report\BASICS-PQ-VPM-15.pdf"           #### File Relative Path
    
    print("Starting extraction...")
    data = extractor.extract_from_pdf(pdf_path)
    print("Extraction complete.")
    
    # Validate extraction
    validation = extractor.validate_extraction(data)
    
    # Export to JSON - auto-named based on script ID
    json_file = extractor.export_to_json(data)