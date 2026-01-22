"""
Test script to validate the PDF comparison system
Run this to test your extraction and comparison logic
"""

from backend.compare.extractor_client import extract_client_pdf
from backend.compare.extractor_executed import extract_executed_pdf
from backend.compare.comparator import compare_scripts
import json


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_client_extraction(pdf_path: str):
    """Test client PDF extraction"""
    print_section("CLIENT PDF EXTRACTION")
    
    try:
        client_script = extract_client_pdf(pdf_path)
        
        print(f"\n✓ Successfully extracted client PDF")
        print(f"  - Setup Steps: {len(client_script.setup_steps)}")
        print(f"  - Execution Steps: {len(client_script.execution_steps)}")
        
        # Show first few setup steps
        if client_script.setup_steps:
            print("\n  First 3 Setup Steps:")
            for step in client_script.setup_steps[:3]:
                print(f"    {step.step_number}. {step.procedure[:60]}...")
        
        # Show first few execution steps
        if client_script.execution_steps:
            print("\n  First 3 Execution Steps:")
            for step in client_script.execution_steps[:3]:
                print(f"    {step.step_number}. {step.procedure[:40]}...")
                print(f"       Expected: {step.expected_results[:40]}...")
        
        return client_script
        
    except Exception as e:
        print(f"\n✗ Error extracting client PDF: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_executed_extraction(pdf_path: str):
    """Test executed PDF extraction"""
    print_section("EXECUTED PDF EXTRACTION")
    
    try:
        executed_script = extract_executed_pdf(pdf_path)
        
        print(f"\n✓ Successfully extracted executed PDF")
        print(f"  - Pre-Test Setup Steps: {len(executed_script.pre_test_setup)}")
        print(f"  - Execution Steps: {len(executed_script.execution_steps)}")
        
        # Show first few pre-test steps
        if executed_script.pre_test_setup:
            print("\n  First 3 Pre-Test Setup Steps:")
            for step in executed_script.pre_test_setup[:3]:
                print(f"    {step.step_number}. {step.procedure[:60]}...")
        
        # Show first few execution steps
        if executed_script.execution_steps:
            print("\n  First 3 Execution Steps:")
            for step in executed_script.execution_steps[:3]:
                print(f"    {step.step_number}. {step.procedure[:40]}...")
                print(f"       Expected: {step.expected_results[:40]}...")
                print(f"       Actual: {step.actual_results[:40]}...")
                print(f"       Status: {step.pass_fail}")
        
        return executed_script
        
    except Exception as e:
        print(f"\n✗ Error extracting executed PDF: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_comparison(client_script, executed_script):
    """Test comparison logic"""
    print_section("COMPARISON RESULTS")
    
    try:
        diffs = compare_scripts(client_script, executed_script)
        
        if not diffs:
            print("\n✓ No differences found - PDFs match perfectly!")
        else:
            print(f"\n⚠ Found {len(diffs)} difference(s):\n")
            for i, diff in enumerate(diffs, 1):
                print(f"{i}. {diff}\n")
        
        return diffs
        
    except Exception as e:
        print(f"\n✗ Error during comparison: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main test function"""
    print_section("PDF COMPARISON SYSTEM TEST")
    
    # UPDATE THESE PATHS TO YOUR ACTUAL PDF FILES
    client_pdf_path = "path/to/your/client_script.pdf"
    executed_pdf_path = "path/to/your/executed_script.pdf"
    
    print(f"\nClient PDF: {client_pdf_path}")
    print(f"Executed PDF: {executed_pdf_path}")
    
    # Test client extraction
    client_script = test_client_extraction(client_pdf_path)
    
    if not client_script:
        print("\n✗ Client extraction failed. Stopping test.")
        return
    
    # Test executed extraction
    executed_script = test_executed_extraction(executed_pdf_path)
    
    if not executed_script:
        print("\n✗ Executed extraction failed. Stopping test.")
        return
    
    # Test comparison
    diffs = test_comparison(client_script, executed_script)
    
    print_section("TEST COMPLETE")
    print("\nSummary:")
    print(f"  Client Setup Steps: {len(client_script.setup_steps)}")
    print(f"  Client Execution Steps: {len(client_script.execution_steps)}")
    print(f"  Executed Pre-Test Steps: {len(executed_script.pre_test_setup)}")
    print(f"  Executed Execution Steps: {len(executed_script.execution_steps)}")
    
    if diffs is not None:
        print(f"  Total Differences: {len(diffs)}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()