import re


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_bullets(text: str) -> list[str]:
    lines = text.splitlines()
    bullets = []
    for line in lines:
        if line.strip().startswith("-"):
            bullets.append(normalize_text(line[1:]))
    return bullets

PASS_FAIL_VALUES = {"pass", "fail", "n/a"}

def extract_pass_fail(cells: list[str]) -> str:
    """
    Robustly extract PASS / FAIL / N/A from any cell.
    """
    for cell in cells:
        if not cell:
            continue

        text = cell.strip().lower()

        # Remove timestamps
        text = re.sub(r"\d{2}-[A-Z]{3}-\d{4}.*", "", text)

        if text in PASS_FAIL_VALUES:
            return text.upper()

    return ""