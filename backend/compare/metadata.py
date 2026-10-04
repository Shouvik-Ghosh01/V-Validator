import re


def extract_script_id(text: str) -> str:
    match = re.search(r"Test Script ID\s+([A-Z0-9\-]+)", text)
    return match.group(1) if match else ""