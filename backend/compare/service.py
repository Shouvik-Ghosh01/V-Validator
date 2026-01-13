from backend.compare.extractor_client import extract_client_pdf
from backend.compare.extractor_executed import extract_executed_pdf
from backend.compare.comparator import compare_scripts


def compare_pdfs(client_pdf_path: str, executed_pdf_path: str):
    client_script = extract_client_pdf(client_pdf_path)
    executed_script = extract_executed_pdf(executed_pdf_path)
    return compare_scripts(client_script, executed_script)
