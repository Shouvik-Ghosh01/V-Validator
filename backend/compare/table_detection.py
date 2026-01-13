def identify_table_type(table) -> str:
    if not table or not table[0]:
        return "unknown"

    header = " ".join(str(c or "").lower() for c in table[0])

    if "expected results" in header and "actual results" in header:
        return "execution"

    if "procedure" in header and "complete" in header:
        return "setup"

    return "unknown"