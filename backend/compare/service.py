from compare.extractor_client_basics import extract_client_pdf
from compare.extractor_executed import extract_executed_pdf
from compare.comparator import compare_scripts
from compare.comparator_output import compare_execution_reports
from compare.schemas import ComparisonMode, ExecutedScript
from typing import List, Dict, Any, Union
import traceback


def _compare_template_vs_output(client_pdf_path: str, executed_pdf_path: str) -> Dict[str, Any]:
    """
    TEMPLATE_VS_OUTPUT: compare client PDF with executed PDF and return structured differences

    (This is the original compare_pdfs() implementation, unchanged apart from the
    added "comparison_mode" key on the result.)
    
    Args:
        client_pdf_path: Path to client (template) test script PDF
        executed_pdf_path: Path to executed (V-Assure output) test script PDF
    
    Returns:
        Dictionary with structured comparison results including metadata
    
    Raises:
        Exception: If extraction or comparison fails
    """
    try:
        # Extract client script
        client_script = extract_client_pdf(client_pdf_path)
        
        # Extract executed script
        executed_script = extract_executed_pdf(executed_pdf_path)
        
        # Compare - returns structured data
        comparison_result = compare_scripts(client_script, executed_script)
        
        # Add metadata from both PDFs
        comparison_result["comparison_mode"] = ComparisonMode.TEMPLATE_VS_OUTPUT.value
        comparison_result["client_metadata"] = client_script.metadata
        comparison_result["executed_metadata"] = executed_script.metadata
        
        # Add step counts
        comparison_result["statistics"] = {
            "client": {
                "total_steps": len(client_script.setup_steps) + len(client_script.execution_steps),
                "setup_steps": len(client_script.setup_steps),
                "execution_steps": len(client_script.execution_steps),
            },
            "executed": {
                "total_steps": len(executed_script.pre_test_setup) + len(executed_script.execution_steps),
                "pre_test_setup_steps": len(executed_script.pre_test_setup),
                "execution_steps": len(executed_script.execution_steps),
            }
        }

        # ─── Step data for PdfScreenshotsViewer ─────────────────────────
        #
        # Merge client + executed extraction into a single dict per step
        # so the frontend popup shows all fields without extra API calls.
        #
        # executed_steps: keyed by step_number string
        #   - procedure        → from client (extractor_client_basics)
        #   - expected_results → from client (extractor_client_basics)
        #   - actual_results   → from executed (extractor_executed)
        #   - pass_fail        → from executed (extractor_executed)
        #
        # pts_steps: keyed by step_number string
        #   - procedure        → from executed (extractor_executed) pre_test_setup
        #     (setup instructions as actually recorded in the executed report)

        # Build client lookup: procedure + expected_results
        client_exec_lookup = {
            s.step_number: s for s in client_script.execution_steps
        }

        # Merge execution steps
        merged_exec: Dict[str, Dict[str, Any]] = {}
        all_exec_nums = set(
            s.step_number for s in client_script.execution_steps
        ) | set(
            s.step_number for s in executed_script.execution_steps
        )

        for num in all_exec_nums:
            client_step = client_exec_lookup.get(num)
            exec_step = next(
                (s for s in executed_script.execution_steps if s.step_number == num),
                None,
            )
            merged_exec[str(num)] = {
                "step_number":      num,
                "procedure":        client_step.procedure if client_step else (exec_step.procedure if exec_step else ""),
                "expected_results": client_step.expected_results if client_step else (exec_step.expected_results if exec_step else ""),
                "actual_results":   exec_step.actual_results if exec_step else "",
                "pass_fail":        exec_step.pass_fail if exec_step else "",
            }

        comparison_result["executed_steps"] = merged_exec

        # PTS steps — setup instructions from the executed report
        comparison_result["pts_steps"] = {
            str(s.step_number): {
                "step_number": s.step_number,
                "procedure":   s.procedure,
            }
            for s in executed_script.pre_test_setup
        }

        return comparison_result
        
    except Exception as e:
        # Re-raise with more context
        error_msg = f"PDF comparison failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        traceback.print_exc()
        raise Exception(error_msg) from e


def _executed_stats(script: ExecutedScript) -> Dict[str, int]:
    return {
        "total_steps": len(script.pre_test_setup) + len(script.execution_steps),
        "pre_test_setup_steps": len(script.pre_test_setup),
        "execution_steps": len(script.execution_steps),
    }


def _executed_step_maps(script: ExecutedScript) -> Dict[str, Dict[str, Any]]:
    """Step data keyed by step_number string, straight from ONE executed report."""
    return {
        "execution": {
            str(s.step_number): {
                "step_number":      s.step_number,
                "procedure":        s.procedure,
                "expected_results": s.expected_results,
                "actual_results":   s.actual_results,
                "pass_fail":        s.pass_fail,
            }
            for s in script.execution_steps
        },
        "pts": {
            str(s.step_number): {
                "step_number": s.step_number,
                "procedure":   s.procedure,
            }
            for s in script.pre_test_setup
        },
    }


def _compare_output_vs_output(pdf_a_path: str, pdf_b_path: str) -> Dict[str, Any]:
    """
    OUTPUT_VS_OUTPUT: both PDFs are V-Assure executed reports (run A vs run B).

    Both go through extract_executed_pdf(). The client/template extractor is
    never used here.
    """
    try:
        output_a = extract_executed_pdf(pdf_a_path)
        output_b = extract_executed_pdf(pdf_b_path)

        result = compare_execution_reports(output_a, output_b)

        steps_a = _executed_step_maps(output_a)
        steps_b = _executed_step_maps(output_b)

        result["output_a_metadata"] = output_a.metadata
        result["output_b_metadata"] = output_b.metadata
        result["statistics"] = {
            "output_a": _executed_stats(output_a),
            "output_b": _executed_stats(output_b),
        }
        result["output_a_steps"] = steps_a["execution"]
        result["output_b_steps"] = steps_b["execution"]
        result["output_a_pts_steps"] = steps_a["pts"]
        result["output_b_pts_steps"] = steps_b["pts"]

        return result

    except Exception as e:
        error_msg = f"PDF comparison failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        traceback.print_exc()
        raise Exception(error_msg) from e


def compare_pdfs(
    pdf_a_path: str,
    pdf_b_path: str,
    mode: Union[ComparisonMode, str] = ComparisonMode.TEMPLATE_VS_OUTPUT,
) -> Dict[str, Any]:
    """
    Compare two PDFs. What the PDFs *are* depends on ``mode``:

      template_vs_output (default, the original behaviour)
          pdf_a = client/template script, pdf_b = executed output report

      output_vs_output
          pdf_a = executed output report A, pdf_b = executed output report B

    Existing two-argument callers keep the original Template-vs-Output behaviour.
    """
    mode = ComparisonMode(mode)  # ValueError on an unknown mode

    if mode is ComparisonMode.OUTPUT_VS_OUTPUT:
        return _compare_output_vs_output(pdf_a_path, pdf_b_path)
    return _compare_template_vs_output(pdf_a_path, pdf_b_path)


def compare_pdfs_legacy(client_pdf_path: str, executed_pdf_path: str) -> List[str]:
    """
    Legacy function that returns differences as list of strings
    For backward compatibility with old API responses
    
    Args:
        client_pdf_path: Path to client test script PDF
        executed_pdf_path: Path to executed test script PDF
    
    Returns:
        List of difference strings
    """
    try:
        # Get structured comparison
        result = compare_pdfs(client_pdf_path, executed_pdf_path)
        
        # Convert to legacy format (list of strings)
        differences = []
        
        # Process setup differences
        for step_num, step_diffs in result.get("setup_differences", {}).items():
            for diff in step_diffs:
                if diff["type"] == "missing":
                    differences.append(f"[SETUP] Step {step_num} missing in executed PDF")
                elif diff["type"] == "procedure_mismatch":
                    differences.append(
                        f"[SETUP] Step {step_num} procedure mismatch\n"
                        f"  Client: {diff['client']}\n"
                        f"  Executed: {diff['executed']}"
                    )
        
        # Process execution differences
        for step_num, step_diffs in result.get("execution_differences", {}).items():
            for diff in step_diffs:
                if diff["type"] == "missing":
                    differences.append(f"[EXECUTION] Step {step_num} missing in executed PDF")
                elif diff["type"] == "procedure_mismatch":
                    differences.append(
                        f"[EXECUTION] Step {step_num} procedure mismatch\n"
                        f"  Client Procedure: {diff['client']}\n"
                        f"  Executed Procedure: {diff['executed']}"
                    )
                elif diff["type"] == "expected_mismatch":
                    differences.append(
                        f"[EXECUTION] Step {step_num} expected results mismatch (Client vs Executed)\n"
                        f"  Client Expected: {diff['client']}\n"
                        f"  Executed Expected: {diff['executed']}"
                    )
                elif diff["type"] == "expected_vs_actual":
                    differences.append(
                        f"[EXECUTION] Step {step_num} expected vs actual mismatch\n"
                        f"  Client Expected: {diff['client_expected']}\n"
                        f"  Executed Actual: {diff['executed_actual']}"
                    )
        
        return differences
        
    except Exception as e:
        return []


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
                "metadata": script.metadata,
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
                "metadata": script.metadata,
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