"""
Test Script PDF Extractor - Veeva Basics Template Format
Fixes:
  - PTS extraction: uses pdfplumber words() + bbox intersection to read
    the PTS cell content accurately (table cell text was being dropped)
  - PTS steps: split on numbered pattern even when all on one line
"""

import pdfplumber
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class SetupStep:
    step_number: int
    procedure: str


@dataclass
class ExecutionStep:
    step_number: int
    procedure: str
    expected_results: str


@dataclass
class TestScriptMetadata:
    script_id: str
    title: str
    description: str
    run_number: str


@dataclass
class TestScriptData:
    metadata: TestScriptMetadata
    setup_steps: List[SetupStep]
    execution_steps: List[ExecutionStep]
    extraction_timestamp: str
    source_file: str
    total_setup_steps: int
    total_execution_steps: int
    total_pages: int


class TableBasedExtractor:

    def __init__(self, debug=False):
        self.debug = debug
        self.log_messages = []

    def log(self, msg: str):
        self.log_messages.append(msg)
        if self.debug:
            print(msg)

    # ── Main entry point ──────────────────────────────────────────────────────

    def extract_from_pdf(self, pdf_path: str) -> TestScriptData:
        with pdfplumber.open(pdf_path) as pdf:
            # Metadata + PTS from pages 1 and 2 (0-indexed)
            p0 = pdf.pages[0]
            p1 = pdf.pages[1] if len(pdf.pages) > 1 else p0

            metadata = self._extract_metadata(p0, p1)
            setup_steps = self._extract_pts(p0, p1)

            # Execution steps from all pages
            execution_steps = []
            seen_steps = set()
            for page_num, page in enumerate(pdf.pages, 1):
                for table in (page.extract_tables() or []):
                    if not table or len(table) < 2:
                        continue
                    if self._identify_table_type(table) == "execution":
                        for step in self._parse_execution_table(table, page_num):
                            if step.step_number not in seen_steps:
                                seen_steps.add(step.step_number)
                                execution_steps.append(step)

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
                total_pages=len(pdf.pages),
            )

    # ── Metadata ──────────────────────────────────────────────────────────────

    def _extract_metadata(self, p0, p1) -> TestScriptMetadata:
        text = (p1.extract_text() or "") + " " + (p0.extract_text() or "")

        sid = ""
        m = re.search(r'Test Script ID\s+([A-Z0-9][A-Z0-9\-]+)', text)
        if m:
            sid = m.group(1).strip()
        if not sid:
            m = re.search(r'(BASICS-[A-Z0-9\-]+)', text)
            if m:
                sid = m.group(1).strip()

        title = ""
        m = re.search(r'Title\s+(.+?)(?:Build Number|Description|Vault Name|\n)', text)
        if m:
            title = m.group(1).strip()

        desc = ""
        m = re.search(r'Description\s+(.+?)(?:Build Number|Run Number|Vault Name|\n)', text, re.DOTALL)
        if m:
            desc = re.sub(r'\s+', ' ', m.group(1).strip())

        run = ""
        m = re.search(r'Run Number\s+(\S+)', text)
        if m:
            run = m.group(1).strip()

        return TestScriptMetadata(script_id=sid, title=title, description=desc, run_number=run)

    # ── PTS extraction ────────────────────────────────────────────────────────

    def _extract_pts(self, p0, p1) -> List[SetupStep]:
        """
        Try multiple strategies to extract PTS steps, most reliable first.
        """
        steps = []

        # Strategy 1: find the PTS cell in tables using pdfplumber words()
        for page in [p1, p0]:
            steps = self._pts_from_table_words(page)
            if steps:
                self.log(f"PTS via table words: {len(steps)} steps")
                return steps

        # Strategy 2: extract_tables() cell content (multiline preserved)
        for page in [p1, p0]:
            steps = self._pts_from_table_cells(page)
            if steps:
                self.log(f"PTS via table cells: {len(steps)} steps")
                return steps

        # Strategy 3: raw page text fallback
        for page in [p1, p0]:
            steps = self._pts_from_raw_text(page)
            if steps:
                self.log(f"PTS via raw text: {len(steps)} steps")
                return steps

        self.log("WARNING: No PTS steps found")
        return []

    def _pts_from_table_words(self, page) -> List[SetupStep]:
        """
        Use pdfplumber's words() within detected table cell bboxes.
        This gives the full text including wrapped lines that extract_tables
        sometimes misses.
        """
        tables = page.find_tables()
        if not tables:
            return []

        all_words = page.extract_words(
            x_tolerance=3,
            y_tolerance=3,
            keep_blank_chars=False,
            use_text_flow=False,
        )

        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell is None:
                        continue
                    x0, top, x1, bottom = cell

                    # Get label text of this cell
                    label_words = [
                        w['text'] for w in all_words
                        if w['x0'] >= x0 and w['x1'] <= x1
                        and w['top'] >= top and w['bottom'] <= bottom
                    ]
                    label_text = ' '.join(label_words)

                    if not re.search(r'pre.?test\s+setup', label_text, re.IGNORECASE):
                        continue

                    # Found the PTS label cell — now look for the content cell
                    # (next cell in same row with larger width)
                    row_cells = [c for c in row.cells if c is not None]
                    label_idx = row_cells.index(cell) if cell in row_cells else -1

                    for content_cell in row_cells[label_idx + 1:]:
                        cx0, ctop, cx1, cbottom = content_cell
                        content_words = [
                            w for w in all_words
                            if w['x0'] >= cx0 - 2 and w['x1'] <= cx1 + 2
                            and w['top'] >= ctop - 2 and w['bottom'] <= cbottom + 2
                        ]
                        if not content_words:
                            continue

                        # Sort words by top (y) then left (x) to reconstruct reading order
                        content_words.sort(key=lambda w: (round(w['top']), w['x0']))

                        # Group into lines by Y proximity
                        lines = []
                        cur_line = []
                        cur_y = None
                        for w in content_words:
                            y = round(w['top'])
                            if cur_y is None or abs(y - cur_y) <= 4:
                                cur_line.append(w['text'])
                                cur_y = y
                            else:
                                if cur_line:
                                    lines.append(' '.join(cur_line))
                                cur_line = [w['text']]
                                cur_y = y
                        if cur_line:
                            lines.append(' '.join(cur_line))

                        pts_text = '\n'.join(lines)
                        steps = self._parse_pts_text(pts_text)
                        if steps:
                            return steps

        return []

    def _pts_from_table_cells(self, page) -> List[SetupStep]:
        """Use extract_tables() and look for PTS cell."""
        for table in (page.extract_tables() or []):
            for row in table:
                if not row:
                    continue
                for col_idx, cell in enumerate(row):
                    cell_text = self._clean_cell(cell)
                    if not re.search(r'pre.?test\s+setup', cell_text, re.IGNORECASE):
                        continue
                    # Look in adjacent cells for the numbered list
                    for look_col in range(col_idx + 1, len(row)):
                        content = self._clean_cell_multiline(row[look_col])
                        if content and len(content) > 30:
                            steps = self._parse_pts_text(content)
                            if steps:
                                return steps
                    # Try the cell itself
                    if len(cell_text) > 60:
                        steps = self._parse_pts_text(cell_text)
                        if steps:
                            return steps
        return []

    def _pts_from_raw_text(self, page) -> List[SetupStep]:
        """Fallback: scan raw extracted text for PTS section."""
        text = page.extract_text() or ""
        m = re.search(
            r'Pre-?Test\s+Setup\s*(?:\(PTS\))?\s*\n?(.*?)(?:\n\s*\n\s*\n|\Z|Pre-Approved|Veeva Systems)',
            text, re.DOTALL | re.IGNORECASE
        )
        if not m:
            return []
        return self._parse_pts_text(m.group(1).strip())

    # ── PTS text parser ───────────────────────────────────────────────────────

    def _parse_pts_text(self, text: str) -> List[SetupStep]:
        """
        Parse numbered PTS items from text, handling both:
          - Multiline text (each item on its own line)
          - Flat text (all items concatenated, e.g. "1. Ensure... 2. Ensure...")
        """
        if not text or not text.strip():
            return []

        # Normalize
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Try to split on numbered boundaries regardless of newlines
        # Pattern: 1 or 2 digit number followed by period/paren and space
        parts = re.split(r'(?=\b\d{1,2}[.)]\s)', text)

        steps = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.match(r'^(\d{1,2})[.)]\s+(.+)', part, re.DOTALL)
            if not m:
                continue
            num = int(m.group(1))
            proc = re.sub(r'\s+', ' ', m.group(2).strip())
            if len(proc) > 5:
                steps.append(SetupStep(step_number=num, procedure=proc))

        if steps:
            return steps

        # Fallback: line-by-line parsing
        lines = [l.strip() for l in text.split('\n')]
        current_num = None
        current_lines = []

        def flush():
            if current_num is not None and current_lines:
                proc = re.sub(r'\s+', ' ', ' '.join(current_lines).strip())
                if proc:
                    steps.append(SetupStep(step_number=current_num, procedure=proc))

        for line in lines:
            if not line:
                continue
            m = re.match(r'^(\d{1,2})[.)]\s+(.+)$', line)
            if m:
                flush()
                current_num = int(m.group(1))
                current_lines = [m.group(2).strip()]
            elif current_num is not None:
                current_lines.append(line)

        flush()
        return steps

    # ── Execution table ───────────────────────────────────────────────────────

    def _identify_table_type(self, table: List[List]) -> str:
        if not table or not table[0]:
            return "unknown"
        header = ' '.join([str(c or '') for c in table[0]]).lower()
        if "expected results" in header or "expected result" in header:
            return "execution"
        if ("actual results" in header or "actual result" in header) and "complete" in header:
            return "setup_old"
        return "unknown"

    def _parse_execution_table(self, table: List[List], page_num: int) -> List[ExecutionStep]:
        steps = []
        for row in table[1:]:
            if not row or len(row) < 3:
                continue
            cells = [self._clean_cell(c) for c in row]
            non_empty = [(i, c) for i, c in enumerate(cells) if c]
            if not non_empty:
                continue

            step_num = None
            step_num_idx = None
            for i, c in non_empty:
                if c.isdigit():
                    step_num = int(c)
                    step_num_idx = i
                    break

            if step_num is None:
                continue

            SKIP = {'pass', 'fail', 'n/a', 'yes', 'no', '✓', 'x', 'pass / fail / n/a'}
            remaining = [c for i, c in non_empty if i > step_num_idx and c.lower() not in SKIP]

            procedure = remaining[0] if len(remaining) >= 1 else ""
            expected = remaining[1] if len(remaining) >= 2 else ""

            if procedure:
                steps.append(ExecutionStep(step_number=step_num, procedure=procedure, expected_results=expected))
        return steps

    # ── Cell helpers ──────────────────────────────────────────────────────────

    def _clean_cell(self, cell) -> str:
        if cell is None:
            return ""
        return re.sub(r'\s+', ' ', str(cell).strip().replace('\n', ' ')).strip()

    def _clean_cell_multiline(self, cell) -> str:
        if cell is None:
            return ""
        text = str(cell).strip()
        return re.sub(r'\n{3,}', '\n\n', text).strip()

    # ── Export ────────────────────────────────────────────────────────────────

    def _sanitize_filename(self, script_id: str) -> str:
        safe = re.sub(r'[^\w\-]', '_', script_id)
        return re.sub(r'_+', '_', safe).strip('_') or "unknown_script"

    def export_to_json(self, data: TestScriptData, output_path: str = None) -> str:
        if output_path is None:
            output_path = f"{self._sanitize_filename(data.metadata.script_id)}.json"
        data_dict = {
            'metadata': asdict(data.metadata),
            'setup_steps': [asdict(s) for s in data.setup_steps],
            'execution_steps': [asdict(s) for s in data.execution_steps],
            'extraction_timestamp': data.extraction_timestamp,
            'source_file': data.source_file,
            'stats': {
                'total_setup_steps': data.total_setup_steps,
                'total_execution_steps': data.total_execution_steps,
                'total_pages': data.total_pages,
            },
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, indent=2, ensure_ascii=False)
        print(f"✓ Exported: {output_path}")
        return output_path

    def validate_extraction(self, data: TestScriptData) -> Dict:
        issues, warnings = [], []
        if not data.metadata.script_id:
            issues.append("Missing Script ID")
        if data.total_setup_steps == 0:
            warnings.append("No PTS setup steps found")
        if data.total_execution_steps == 0:
            issues.append("No execution steps found")
        exec_nums = [s.step_number for s in data.execution_steps]
        if exec_nums:
            missing = set(range(1, max(exec_nums) + 1)) - set(exec_nums)
            if missing:
                warnings.append(f"Missing execution steps: {sorted(missing)}")
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'stats': {
                'setup_steps': data.total_setup_steps,
                'execution_steps': data.total_execution_steps,
                'pages_processed': data.total_pages,
            },
        }


if __name__ == "__main__":
    extractor = TableBasedExtractor(debug=True)
    pdf_path = "Template.pdf"
    print("Extracting...")
    data = extractor.extract_from_pdf(pdf_path)
    print(f"PTS steps: {data.total_setup_steps}")
    for s in data.setup_steps:
        print(f"  [{s.step_number}] {s.procedure[:80]}...")
    print(f"Execution steps: {data.total_execution_steps}")
    print("Validation:", extractor.validate_extraction(data))
    extractor.export_to_json(data)
