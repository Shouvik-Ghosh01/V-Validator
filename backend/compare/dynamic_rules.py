import re

# Phrases that indicate dynamic runtime info is expected
DYNAMIC_PATTERNS = [
    r"is recorded",
    r"is generated",
    r"is created",
    r"system displays",
    r"record name",
    r"id is generated",
]

# Regexes to extract useful runtime info
DYNAMIC_VALUE_PATTERNS = {
    "application_id": r"Application[_\s]?(\d+)",
    "record_name": r"Record Name\s*[:\-]\s*(\w+)",
}


def allows_dynamic_suffix(expected: str) -> bool:
    expected_lower = expected.lower()
    return any(re.search(p, expected_lower) for p in DYNAMIC_PATTERNS)


def extract_dynamic_values(text: str) -> dict:
    extracted = {}
    for key, pattern in DYNAMIC_VALUE_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted[key] = match.group(0)
    return extracted