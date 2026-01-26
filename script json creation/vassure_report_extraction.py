"""
Executed Test Script PDF Extractor
Extracts structured data from executed test script PDFs (25R3 format)
"""

import pdfplumber
import re
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class PreTestStep:
    """Structure for Pre-Test Setup Steps"""
    step_number: int
    procedure: str


@dataclass
class ExecutionStep:
    """Structure for Execution Steps"""
    step_number: int
    procedure: str
    expected_results: str
    actual_results: str


@dataclass
class TestScriptMetadata:
    """Test script header metadata"""
    script_id: str
    title: str
    description: str
    start_time: str
    end_time: str
    script_run_time: str  # Calculated difference


@dataclass
class ExecutedTestScriptData:
    """Complete executed test script structure"""
    metadata: TestScriptMetadata
    pre_test_setup: List[PreTestStep]
    execution_steps: List[ExecutionStep]
    extraction_timestamp: str
    source_file: str
    
    # Statistics
    total_pre_test_steps: int
    total_execution_steps: int
    total_pages: int


class ExecutedScriptExtractor:
    """Extract structured data from executed test script PDFs"""
    
    def __init__(self, debug=False):
        self.debug = debug
        self.log_messages = []
        
    def log(self, message: str):
        """Internal logging"""
        self.log_messages.append(message)
        if self.debug:
            print(message)
    
    def extract_from_pdf(self, pdf_path: str) -> ExecutedTestScriptData:
        """
        Main extraction method
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            ExecutedTestScriptData object with all extracted information
        """
        with pdfplumber.open(pdf_path) as pdf:
            # Skip first page, extract metadata from second page
            if len(pdf.pages) < 2:
                raise ValueError("PDF must have at least 2 pages")
            
            metadata = self._extract_metadata(pdf.pages[1])
            
            pre_test_steps = []
            execution_steps = []
            
            # Process pages starting from page 2
            for page_num, page in enumerate(pdf.pages[1:], 2):
                page_text = page.extract_text()
                
                # Extract Pre-Test Setup steps from text
                if "Pre-Test Setup (PTS)" in page_text or "Pre-Test Setup" in page_text:
                    steps = self._extract_pre_test_setup(page_text, page_num)
                    pre_test_steps.extend(steps)
                
                # Extract execution steps from tables
                tables = page.extract_tables()
                
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    
                    table_type = self._identify_table_type(table)
                    
                    if table_type == "execution":
                        steps = self._parse_execution_table(table, page_num)
                        execution_steps.extend(steps)
            
            # Sort and deduplicate steps
            pre_test_steps = self._deduplicate_steps(pre_test_steps)
            execution_steps = self._deduplicate_execution_steps(execution_steps)
            
            return ExecutedTestScriptData(
                metadata=metadata,
                pre_test_setup=pre_test_steps,
                execution_steps=execution_steps,
                extraction_timestamp=datetime.now().isoformat(),
                source_file=pdf_path,
                total_pre_test_steps=len(pre_test_steps),
                total_execution_steps=len(execution_steps),
                total_pages=len(pdf.pages)
            )
    
    def _extract_metadata(self, page) -> TestScriptMetadata:
        """Extract header metadata from second page"""
        text = page.extract_text()
        
        # Extract Script ID
        script_id_match = re.search(r'Test Script ID\s+([A-Z0-9\-]+)', text)
        script_id = script_id_match.group(1) if script_id_match else ""
        
        # Extract Title
        title_match = re.search(r'Title\s+(.+?)(?:\n|Description)', text)
        title = title_match.group(1).strip() if title_match else ""
        
        # Extract Description
        desc_match = re.search(r'Description\s+(.+?)(?:\n|Build Number)', text)
        description = desc_match.group(1).strip() if desc_match else ""
        
        # Extract Start Time
        start_match = re.search(r'Start Time\s+(.+?)(?:\n|End Time)', text)
        start_time = start_match.group(1).strip() if start_match else ""
        
        # Extract End Time
        end_match = re.search(r'End Time\s+(.+?)(?:\n|Pre-Test)', text)
        end_time = end_match.group(1).strip() if end_match else ""
        
        # Calculate runtime
        script_run_time = self._calculate_runtime(start_time, end_time)
        
        return TestScriptMetadata(
            script_id=script_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            script_run_time=script_run_time
        )
    
    def _calculate_runtime(self, start_time: str, end_time: str) -> str:
        """Calculate the difference between start and end time"""
        try:
            # Parse format: "22-OCT-2025 10:38:31 GMT-07:00"
            start_dt = datetime.strptime(start_time.split(' GMT')[0], "%d-%b-%Y %H:%M:%S")
            end_dt = datetime.strptime(end_time.split(' GMT')[0], "%d-%b-%Y %H:%M:%S")
            
            diff = end_dt - start_dt
            
            # Format as HH:MM:SS
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception as e:
            self.log(f"Error calculating runtime: {e}")
            return "00:00:00"
    
    def _extract_pre_test_setup(self, page_text: str, page_num: int) -> List[PreTestStep]:
        """Extract Pre-Test Setup steps from text"""
        steps = []
        
        # Find the PTS section
        pts_match = re.search(r'Pre-Test Setup \(PTS\)\s+(.+?)(?:PTS Screenshots|Executed Test Script|$)', 
                             page_text, re.DOTALL)
        
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
            
            steps.append(PreTestStep(
                step_number=step_num,
                procedure=procedure
            ))
        
        return steps
    
    def _identify_table_type(self, table: List[List[str]]) -> str:
        """Identify if table is execution steps table"""
        if not table or not table[0]:
            return "unknown"
        
        header_row = ' '.join([str(cell or '') for cell in table[0]]).lower()
        
        # Execution table has: Step #, Procedure, Expected Results, Actual Results, Pass/Fail
        if "procedure" in header_row and "expected results" in header_row and "actual results" in header_row:
            return "execution"
        
        return "unknown"
    
    def _parse_execution_table(self, table: List[List[str]], page_num: int) -> List[ExecutionStep]:
        """Parse an execution steps table"""
        steps = []
        
        # Skip header row
        for row_idx, row in enumerate(table[1:], 1):
            if not row or len(row) < 4:
                continue
            
            # Clean cells
            cells = [self._clean_cell(cell) for cell in row]
            
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
            for idx, cell in remaining_cells:
                lower_cell = cell.lower()
                # Skip Pass/Fail/N/A and timestamp patterns
                if lower_cell in ['pass', 'fail', 'n/a'] or re.match(r'\d{2}-[A-Z]{3}-\d{4}', cell):
                    continue
                content_cells.append(cell)
            
            # First cell is procedure, second is expected, third is actual
            if len(content_cells) >= 1:
                procedure = content_cells[0]
            if len(content_cells) >= 2:
                expected_results = content_cells[1]
            if len(content_cells) >= 3:
                actual_results = content_cells[2]
            
            if procedure:
                steps.append(ExecutionStep(
                    step_number=step_num,
                    procedure=procedure,
                    expected_results=expected_results,
                    actual_results=actual_results
                ))
        
        return steps
    
    def _clean_cell(self, cell) -> str:
        """Clean and normalize cell content"""
        if cell is None:
            return ""
        
        text = str(cell).strip()
        text = text.replace('\n', ' ')
        text = re.sub(r' +', ' ', text)
        
        return text.strip()
    
    def _deduplicate_steps(self, steps: List[PreTestStep]) -> List[PreTestStep]:
        """Remove duplicate steps and sort by step number"""
        seen = {}
        for step in steps:
            if step.step_number not in seen:
                seen[step.step_number] = step
        
        return sorted(seen.values(), key=lambda x: x.step_number)
    
    def _deduplicate_execution_steps(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Remove duplicate execution steps and sort by step number"""
        seen = {}
        for step in steps:
            if step.step_number not in seen:
                seen[step.step_number] = step
        
        return sorted(seen.values(), key=lambda x: x.step_number)
    
    def _sanitize_filename(self, script_id: str) -> str:
        """Sanitize script ID to create a valid filename"""
        safe_name = re.sub(r'[^\w\-]', '_', script_id)
        safe_name = re.sub(r'_+', '_', safe_name)
        safe_name = safe_name.strip('_')
        return safe_name if safe_name else "unknown_script"
    
    def export_to_json(self, data: ExecutedTestScriptData, output_path: str = None):
        """Export extracted data to JSON (auto-named by script ID if no path provided)"""
        if output_path is None:
            safe_script_id = self._sanitize_filename(data.metadata.script_id)
            output_path = f"{safe_script_id}.json"
        
        data_dict = {
            'metadata': asdict(data.metadata),
            'pre_test_setup': [asdict(step) for step in data.pre_test_setup],
            'execution_steps': [asdict(step) for step in data.execution_steps],
            'extraction_timestamp': data.extraction_timestamp,
            'source_file': data.source_file,
            'stats': {
                'total_pre_test_steps': data.total_pre_test_steps,
                'total_execution_steps': data.total_execution_steps,
                'total_pages': data.total_pages
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Exported JSON: {output_path}")
        return output_path
    
    def validate_extraction(self, data: ExecutedTestScriptData) -> Dict:
        """Validate the extracted data"""
        issues = []
        warnings = []
        
        if not data.metadata.script_id:
            issues.append("Missing Script ID")
        if not data.metadata.title:
            warnings.append("Missing Title")
        if data.total_execution_steps == 0:
            issues.append("No execution steps found")
        if data.total_pre_test_steps == 0:
            warnings.append("No pre-test setup steps found")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'stats': {
                'pre_test_steps': data.total_pre_test_steps,
                'execution_steps': data.total_execution_steps,
                'pages_processed': data.total_pages
            }
        }
    
    def generate_extraction_report(self, data: ExecutedTestScriptData, validation: Dict) -> str:
        """Generate a human-readable extraction report"""
        report = []
        report.append("=" * 60)
        report.append("EXECUTED TEST SCRIPT EXTRACTION REPORT")
        report.append("=" * 60)
        report.append(f"\nScript ID: {data.metadata.script_id}")
        report.append(f"Title: {data.metadata.title}")
        report.append(f"Description: {data.metadata.description}")
        report.append(f"Start Time: {data.metadata.start_time}")
        report.append(f"End Time: {data.metadata.end_time}")
        report.append(f"Script Run Time: {data.metadata.script_run_time}")
        report.append(f"\nSource File: {data.source_file}")
        report.append(f"Extracted: {data.extraction_timestamp}")
        report.append(f"Total Pages: {data.total_pages}")
        
        report.append("\n" + "-" * 60)
        report.append("EXTRACTION STATISTICS")
        report.append("-" * 60)
        report.append(f"Pre-Test Setup Steps: {data.total_pre_test_steps}")
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
    extractor = ExecutedScriptExtractor(debug=True)
    
    pdf_path = "script json creation\Report\LIMS02REPORT.pdf"
    
    print("Starting extraction...")
    data = extractor.extract_from_pdf(pdf_path)
    print("\nExtraction complete.")
    
    validation = extractor.validate_extraction(data)
    
    json_file = extractor.export_to_json(data)