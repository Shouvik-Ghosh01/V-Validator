"""
Debug utility to inspect PDF structure and extraction process
Helps diagnose extraction issues
"""

import pdfplumber
import json


def inspect_pdf_structure(pdf_path: str, output_file: str = "pdf_structure.json"):
    """
    Inspect PDF structure and save detailed information
    Useful for debugging extraction issues
    """
    
    structure = {
        "file": pdf_path,
        "pages": []
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        structure["total_pages"] = len(pdf.pages)
        
        for page_num, page in enumerate(pdf.pages, 1):
            page_info = {
                "page_number": page_num,
                "text_preview": None,
                "tables": []
            }
            
            # Extract text
            text = page.extract_text()
            if text:
                # First 500 chars
                page_info["text_preview"] = text[:500]
            
            # Extract tables
            tables = page.extract_tables()
            
            for table_idx, table in enumerate(tables, 1):
                if not table:
                    continue
                
                table_info = {
                    "table_number": table_idx,
                    "rows": len(table),
                    "columns": len(table[0]) if table else 0,
                    "headers": [],
                    "sample_rows": []
                }
                
                # Get headers (first row)
                if table:
                    table_info["headers"] = [str(cell or "") for cell in table[0]]
                    
                    # Get first 3 data rows
                    for row in table[1:4]:
                        table_info["sample_rows"].append([str(cell or "") for cell in row])
                
                page_info["tables"].append(table_info)
            
            structure["pages"].append(page_info)
    
    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(structure, f, indent=2, ensure_ascii=False)
    
    print(f"✓ PDF structure saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("PDF STRUCTURE SUMMARY")
    print("=" * 70)
    print(f"File: {pdf_path}")
    print(f"Total Pages: {structure['total_pages']}")
    
    for page in structure["pages"]:
        print(f"\nPage {page['page_number']}:")
        print(f"  Tables found: {len(page['tables'])}")
        
        for table in page["tables"]:
            print(f"    Table {table['table_number']}: {table['rows']} rows × {table['columns']} cols")
            print(f"      Headers: {table['headers']}")
    
    return structure


def test_table_detection(pdf_path: str):
    """
    Test table type detection on all tables in PDF
    """
    print("\n" + "=" * 70)
    print("TABLE TYPE DETECTION TEST")
    print("=" * 70)
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            
            if not tables:
                continue
            
            print(f"\nPage {page_num}: Found {len(tables)} table(s)")
            
            for table_idx, table in enumerate(tables, 1):
                if not table or not table[0]:
                    continue
                
                # Show headers
                headers = [str(cell or "") for cell in table[0]]
                header_str = " | ".join(headers)
                
                print(f"\n  Table {table_idx}:")
                print(f"    Headers: {header_str}")
                
                # Detect type
                header_text = " ".join(headers).lower()
                
                if "expected results" in header_text and "actual results" in header_text:
                    table_type = "EXECUTION (with actual results)"
                elif "expected results" in header_text:
                    table_type = "EXECUTION (client template)"
                elif "procedure" in header_text and "complete" in header_text:
                    table_type = "SETUP"
                else:
                    table_type = "UNKNOWN"
                
                print(f"    Detected Type: {table_type}")
                
                # Show first data row
                if len(table) > 1:
                    first_row = [str(cell or "")[:30] for cell in table[1]]
                    print(f"    First Row: {first_row}")


def extract_with_debug(pdf_path: str, is_executed: bool = False):
    """
    Extract PDF with detailed debug output
    """
    print("\n" + "=" * 70)
    print(f"EXTRACTION WITH DEBUG - {'EXECUTED' if is_executed else 'CLIENT'} PDF")
    print("=" * 70)
    
    if is_executed:
        from backend.compare.extractor_executed import extract_executed_pdf
        script = extract_executed_pdf(pdf_path)
        
        print(f"\n✓ Extraction complete:")
        print(f"  Pre-Test Setup Steps: {len(script.pre_test_setup)}")
        print(f"  Execution Steps: {len(script.execution_steps)}")
        
        if script.pre_test_setup:
            print("\n  Pre-Test Setup Steps:")
            for step in script.pre_test_setup[:5]:
                print(f"    {step.step_number}. {step.procedure[:60]}...")
        
        if script.execution_steps:
            print("\n  Execution Steps:")
            for step in script.execution_steps[:5]:
                print(f"    {step.step_number}. {step.procedure[:40]}...")
                print(f"       Status: {step.pass_fail}")
    
    else:
        from backend.compare.extractor_client import extract_client_pdf
        script = extract_client_pdf(pdf_path)
        
        print(f"\n✓ Extraction complete:")
        print(f"  Setup Steps: {len(script.setup_steps)}")
        print(f"  Execution Steps: {len(script.execution_steps)}")
        
        if script.setup_steps:
            print("\n  Setup Steps:")
            for step in script.setup_steps[:5]:
                print(f"    {step.step_number}. {step.procedure[:60]}...")
        
        if script.execution_steps:
            print("\n  Execution Steps:")
            for step in script.execution_steps[:5]:
                print(f"    {step.step_number}. {step.procedure[:40]}...")


def main():
    """
    Main debug function - update paths to your PDFs
    """
    print("=" * 70)
    print("PDF EXTRACTION DEBUG UTILITY")
    print("=" * 70)
    
    # UPDATE THESE PATHS
    client_pdf = "path/to/client.pdf"
    executed_pdf = "path/to/executed.pdf"
    
    print("\nWhat would you like to debug?")
    print("1. Inspect client PDF structure")
    print("2. Inspect executed PDF structure")
    print("3. Test table detection on client PDF")
    print("4. Test table detection on executed PDF")
    print("5. Extract client PDF with debug")
    print("6. Extract executed PDF with debug")
    print("7. Run all diagnostics")
    
    choice = input("\nEnter choice (1-7): ").strip()
    
    if choice == "1":
        inspect_pdf_structure(client_pdf, "client_structure.json")
    elif choice == "2":
        inspect_pdf_structure(executed_pdf, "executed_structure.json")
    elif choice == "3":
        test_table_detection(client_pdf)
    elif choice == "4":
        test_table_detection(executed_pdf)
    elif choice == "5":
        extract_with_debug(client_pdf, is_executed=False)
    elif choice == "6":
        extract_with_debug(executed_pdf, is_executed=True)
    elif choice == "7":
        print("\n🔍 Running full diagnostics...")
        inspect_pdf_structure(client_pdf, "client_structure.json")
        inspect_pdf_structure(executed_pdf, "executed_structure.json")
        test_table_detection(client_pdf)
        test_table_detection(executed_pdf)
        extract_with_debug(client_pdf, is_executed=False)
        extract_with_debug(executed_pdf, is_executed=True)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()