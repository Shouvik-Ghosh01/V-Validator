def normalize_blocks(blocks: list[dict]) -> list[dict]:
    """
    Normalizes text for comparison (spacing, bullets, case).
    """
    normalized = []

    for b in blocks:
        text = " ".join(b["text"].split())
        normalized.append({
            **b,
            "norm_text": text.lower()
        })

    return normalized
