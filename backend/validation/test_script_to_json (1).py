"""
Test Script PDF Extractor - Table-Based Version
Extracts structured data from test script PDFs using table detection
"""

import pdfplumber
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SetupStep:
    """Structure for Setup Steps"""
    step_number: int
    procedure: str
    actual_results: str
    complete: str
    raw_text: str
    page_number: int


@dataclass
class ExecutionStep:
    """Structure for Execution Steps"""
    step_number: int
    procedure: str
    expected_results: str
    actual_results: str
    pass_fail: str
    raw_text: str
    page_number: int


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
            in_setup = False
            in_execution = False
            
            setup_steps = []
            execution_steps = []
            
            # Process each page
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                
                # Detect section transitions
                if "Setup Steps" in page_text and not in_execution:
                    in_setup = True
                    if self.debug:
                        print(f"Page {page_num}: Entered Setup Steps section")
                
                if "Execution Steps" in page_text:
                    in_setup = False
                    in_execution = True
                    if self.debug:
                        print(f"Page {page_num}: Entered Execution Steps section")
                
                # Extract tables from current page
                tables = page.extract_tables()
                
                if self.debug:
                    print(f"Page {page_num}: Found {len(tables)} tables")
                
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    
                    # Identify table type by headers
                    table_type = self._identify_table_type(table)
                    
                    if self.debug:
                        print(f"  Table {table_idx + 1}: Type = {table_type}")
                    
                    if table_type == "setup" and in_setup:
                        steps = self._parse_setup_table(table, page_num)
                        setup_steps.extend(steps)
                        
                    elif table_type == "execution" and in_execution:
                        steps = self._parse_execution_table(table, page_num)
                        execution_steps.extend(steps)
            
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
        
        # Get first row (headers) and join
        header_row = ' '.join([str(cell or '') for cell in table[0]]).lower()
        
        # Check for setup table indicators
        if "actual results" in header_row and "complete" in header_row:
            if "expected" not in header_row:  # Setup doesn't have "expected"
                return "setup"
        
        # Check for execution table indicators
        if "expected results" in header_row and "pass" in header_row:
            return "execution"
        
        return "unknown"
    
    def _parse_setup_table(self, table: List[List[str]], page_num: int) -> List[SetupStep]:
        """Parse a setup steps table"""
        steps = []
        
        # Skip header row
        for row_idx, row in enumerate(table[1:], 1):
            if not row or len(row) < 3:
                continue
            
            # Clean cells
            cells = [self._clean_cell(cell) for cell in row]
            
            # Expected columns: Step | Procedure | Actual Results | Complete?
            # But table extraction might vary, so be flexible
            
            # Try to find step number (usually first non-empty cell)
            step_num = None
            step_num_idx = None
            
            for idx, cell in enumerate(cells):
                if cell and cell.isdigit():
                    step_num = int(cell)
                    step_num_idx = idx
                    break
            
            if step_num is None:
                continue
            
            # Extract other fields
            procedure = ""
            actual_results = ""
            complete = ""
            
            # Procedure is typically after step number
            if step_num_idx + 1 < len(cells):
                procedure = cells[step_num_idx + 1]
            
            # Actual Results (often empty in setup)
            if step_num_idx + 2 < len(cells):
                actual_results = cells[step_num_idx + 2]
            
            # Complete? (Yes/No)
            if step_num_idx + 3 < len(cells):
                complete = cells[step_num_idx + 3]
            
            # Sometimes "Complete?" is in the last column
            if not complete and cells[-1] in ["Yes", "No"]:
                complete = cells[-1]
            
            raw_text = " | ".join(cells)
            
            steps.append(SetupStep(
                step_number=step_num,
                procedure=procedure,
                actual_results=actual_results,
                complete=complete,
                raw_text=raw_text,
                page_number=page_num
            ))
        
        return steps
    
    def _parse_execution_table(self, table: List[List[str]], page_num: int) -> List[ExecutionStep]:
        """Parse an execution steps table"""
        steps = []
        
        # Skip header row
        for row_idx, row in enumerate(table[1:], 1):
            if not row or len(row) < 4:
                continue
            
            # Clean cells
            cells = [self._clean_cell(cell) for cell in row]
            
            # Expected columns: Step | Procedure | Expected Results | Actual Results | Pass/Fail/N/A
            
            # Find step number
            step_num = None
            step_num_idx = None
            
            for idx, cell in enumerate(cells):
                if cell and cell.isdigit():
                    step_num = int(cell)
                    step_num_idx = idx
                    break
            
            if step_num is None:
                continue
            
            # Extract fields
            procedure = ""
            expected_results = ""
            actual_results = ""
            pass_fail = ""
            
            # Procedure
            if step_num_idx + 1 < len(cells):
                procedure = cells[step_num_idx + 1]
            
            # Expected Results
            if step_num_idx + 2 < len(cells):
                expected_results = cells[step_num_idx + 2]
            
            # Actual Results
            if step_num_idx + 3 < len(cells):
                actual_results = cells[step_num_idx + 3]
            
            # Pass/Fail/N/A
            if step_num_idx + 4 < len(cells):
                pass_fail = cells[step_num_idx + 4]
            
            # Check last column for Pass/Fail if not found
            if not pass_fail and cells[-1] in ["Pass", "Fail", "N/A", ""]:
                pass_fail = cells[-1]
            
            raw_text = " | ".join(cells)
            
            steps.append(ExecutionStep(
                step_number=step_num,
                procedure=procedure,
                expected_results=expected_results,
                actual_results=actual_results,
                pass_fail=pass_fail,
                raw_text=raw_text,
                page_number=page_num
            ))
        
        return steps
    
    def _clean_cell(self, cell) -> str:
        """Clean and normalize cell content"""
        if cell is None:
            return ""
        
        text = str(cell).strip()
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common artifacts
        text = text.replace('\n', ' ')
        
        return text
    
    def export_to_json(self, data: TestScriptData, output_path: str):
        """Export extracted data to JSON"""
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
    
    def export_to_csv(self, data: TestScriptData, output_prefix: str):
        """Export to CSV files (one for setup, one for execution)"""
        import csv
        
        # Export setup steps
        setup_file = f"{output_prefix}_setup.csv"
        with open(setup_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Step', 'Procedure', 'Actual Results', 'Complete', 'Page'])
            for step in data.setup_steps:
                writer.writerow([
                    step.step_number,
                    step.procedure,
                    step.actual_results,
                    step.complete,
                    step.page_number
                ])
        
        # Export execution steps
        exec_file = f"{output_prefix}_execution.csv"
        with open(exec_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Step', 'Procedure', 'Expected Results', 'Actual Results', 'Pass/Fail', 'Page'])
            for step in data.execution_steps:
                writer.writerow([
                    step.step_number,
                    step.procedure,
                    step.expected_results,
                    step.actual_results,
                    step.pass_fail,
                    step.page_number
                ])
        
        print(f"Exported to {setup_file} and {exec_file}")
    
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
    # Initialize extractor with debug mode
    extractor = TableBasedExtractor(debug=True)
    
    # Extract from PDF
    pdf_path = "BASICS-QA-LIMS-02 VBQ script Jan 2.pdf"
    
    print("Starting extraction...")
    data = extractor.extract_from_pdf(pdf_path)
    
    # Validate extraction
    validation = extractor.validate_extraction(data)
    
    # Generate and print report
    report = extractor.generate_extraction_report(data, validation)
    print("\n" + report)
    
    # Export to JSON
    json_output = "extracted_test_script2.json"
    extractor.export_to_json(data, json_output)
    print(f"\n✓ Exported to JSON: {json_output}")
    
    # Print sample data
    if data.setup_steps:
        print(f"\n--- SAMPLE SETUP STEP (Step {data.setup_steps[0].step_number}) ---")
        print(f"Procedure: {data.setup_steps[0].procedure[:150]}...")
        print(f"Complete: {data.setup_steps[0].complete}")
        print(f"Page: {data.setup_steps[0].page_number}")
    
    if data.execution_steps:
        print(f"\n--- SAMPLE EXECUTION STEP (Step {data.execution_steps[0].step_number}) ---")
        print(f"Procedure: {data.execution_steps[0].procedure[:150]}...")
        print(f"Expected: {data.execution_steps[0].expected_results[:150]}...")
        print(f"Page: {data.execution_steps[0].page_number}")