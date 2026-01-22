from backend.compare.extractor_client import extract_client_pdf
from backend.compare.extractor_executed import extract_executed_pdf
from backend.compare.comparator import compare_scripts
from typing import List, Dict, Any
import traceback


def compare_pdfs(client_pdf_path: str, executed_pdf_path: str) -> List[str]:
    """
    Compare client PDF with executed PDF and return differences
    
    Args:
        client_pdf_path: Path to client (template) test script PDF
        executed_pdf_path: Path to executed (V-Assure output) test script PDF
    
    Returns:
        List of difference strings
    
    Raises:
        Exception: If extraction or comparison fails
    """
    try:
        # Extract client script
        client_script = extract_client_pdf(client_pdf_path)
        
        # Extract executed script
        executed_script = extract_executed_pdf(executed_pdf_path)
        
        # Compare
        differences = compare_scripts(client_script, executed_script)
        
        return differences
        
    except Exception as e:
        # Re-raise with more context
        error_msg = f"PDF comparison failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        traceback.print_exc()
        raise Exception(error_msg) from e


def compare_pdfs_with_details(
    client_pdf_path: str, 
    executed_pdf_path: str
) -> Dict[str, Any]:
    """
    Compare PDFs and return detailed results including statistics
    
    Args:
        client_pdf_path: Path to client test script PDF
        executed_pdf_path: Path to executed test script PDF
    
    Returns:
        Dictionary with differences, statistics, and metadata
    """
    try:
        # Extract scripts
        client_script = extract_client_pdf(client_pdf_path)
        executed_script = extract_executed_pdf(executed_pdf_path)
        
        # Compare
        differences = compare_scripts(client_script, executed_script)
        
        # Build detailed response
        result = {
            "success": True,
            "differences": differences,
            "difference_count": len(differences),
            "statistics": {
                "client": {
                    "setup_steps": len(client_script.setup_steps),
                    "execution_steps": len(client_script.execution_steps),
                },
                "executed": {
                    "pre_test_setup_steps": len(executed_script.pre_test_setup),
                    "execution_steps": len(executed_script.execution_steps),
                }
            },
            "status": "MATCH" if len(differences) == 0 else "MISMATCH"
        }
        
        # Add failure summary if there are differences
        if differences:
            failure_count = sum(1 for d in differences if "did not PASS" in d)
            mismatch_count = len(differences) - failure_count
            
            result["summary"] = {
                "failed_steps": failure_count,
                "mismatched_steps": mismatch_count,
                "total_issues": len(differences)
            }
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "differences": [],
            "difference_count": 0,
            "status": "ERROR"
        }


def validate_pdf_extraction(pdf_path: str, is_executed: bool = False) -> Dict[str, Any]:
    """
    Validate that a PDF can be extracted successfully
    Useful for pre-flight checks
    
    Args:
        pdf_path: Path to PDF file
        is_executed: True if this is an executed script, False if client script
    
    Returns:
        Dictionary with validation results
    """
    try:
        if is_executed:
            script = extract_executed_pdf(pdf_path)
            return {
                "valid": True,
                "type": "executed",
                "statistics": {
                    "pre_test_setup_steps": len(script.pre_test_setup),
                    "execution_steps": len(script.execution_steps),
                }
            }
        else:
            script = extract_client_pdf(pdf_path)
            return {
                "valid": True,
                "type": "client",
                "statistics": {
                    "setup_steps": len(script.setup_steps),
                    "execution_steps": len(script.execution_steps),
                }
            }
    
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "error_type": type(e).__name__
        }