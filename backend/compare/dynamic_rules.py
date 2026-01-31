import re

# -------------------------------------------------
# Phrases that indicate runtime-generated info
# -------------------------------------------------
DYNAMIC_PATTERNS = [
    r"is recorded",
    r"is generated",
    r"is created",
    r"system displays",
    r"record is displayed",
    r"record name",
    r"id is generated",
    r"product forms shown",
]

# -------------------------------------------------
# Regexes to extract runtime-generated values
# -------------------------------------------------
DYNAMIC_VALUE_PATTERNS = {
    "application_id": r"Application[_\s]?(\d+)",

    "record_name": r"Record Name\s*[:\-]\s*([A-Za-z0-9_]+)",

    # NEW: Product Family Record Name
    "product_family_record": r"Product Family record Name\s*is\s*[:\-]?\s*([A-Za-z0-9_]+)",
}


# -------------------------------------------------
# Decide whether dynamic suffix is allowed
# -------------------------------------------------
def allows_dynamic_suffix(expected: str) -> bool:
    expected_lower = expected.lower()
    return any(re.search(pattern, expected_lower) for pattern in DYNAMIC_PATTERNS)


# -------------------------------------------------
# Extract runtime-generated values
# -------------------------------------------------
def extract_dynamic_values(text: str) -> dict:
    extracted = {}

    for key, pattern in DYNAMIC_VALUE_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted[key] = match.group(1)

    return extracted