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


# -------------------------------------------------
# Output-vs-Output support (additive — nothing above is changed)
# -------------------------------------------------
_COMPILED_VALUE_PATTERNS = {
    key: re.compile(pattern, re.IGNORECASE)
    for key, pattern in DYNAMIC_VALUE_PATTERNS.items()
}


def mask_dynamic_values(text: str) -> tuple[str, dict[str, list[str]]]:
    """
    Replace every runtime-generated value recognised by DYNAMIC_VALUE_PATTERNS
    with a stable placeholder.

    Returns (masked_text, {pattern_key: [values in order of appearance]}).

    Unlike extract_dynamic_values() (first match only, used by the
    Template-vs-Output comparator), this finds ALL occurrences, so two runs can
    be compared occurrence-by-occurrence.
    """
    masked = text or ""
    values: dict[str, list[str]] = {}

    for key, rx in _COMPILED_VALUE_PATTERNS.items():
        found: list[str] = []

        def _sub(m: re.Match, _key: str = key, _found: list[str] = found) -> str:
            _found.append(m.group(1))
            whole = m.group(0)
            lo = m.start(1) - m.start(0)
            hi = m.end(1) - m.start(0)
            return whole[:lo] + f"<dynamic:{_key}>" + whole[hi:]

        masked = rx.sub(_sub, masked)
        if found:
            values[key] = found

    return masked, values


def dynamic_value_shape(value: str) -> str:
    """
    Collapse digit runs so 'Product_12345' and 'Product_12387' share a shape.

    Two runtime values are treated as the same kind of generated value only when
    their shapes match. 'Product_1' vs 'Vendor_1' do NOT, so a change in the
    kind of record is still surfaced as a meaningful difference.
    """
    return re.sub(r"\d+", "#", value or "")
