from backend.comparison.pdf_parser import extract_pdf_blocks
from backend.comparison.normalizer import normalize_blocks
from backend.comparison.aligner import align_blocks
from backend.comparison.diff_engine import compute_diffs

def compare_pdfs(input_pdf: str, output_pdf: str) -> dict:
    a_blocks = normalize_blocks(extract_pdf_blocks(input_pdf))
    b_blocks = normalize_blocks(extract_pdf_blocks(output_pdf))

    aligned = align_blocks(a_blocks, b_blocks)
    diffs = compute_diffs(aligned)

    return {
        "total_differences": len(diffs),
        "differences": diffs
    }
