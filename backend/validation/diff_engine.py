def compute_diffs(aligned_blocks):
    diffs = []

    for a, b, score in aligned_blocks:
        if b is None:
            diffs.append({
                "type": "missing_in_output",
                "text": a["text"],
                "page": a["page"]
            })
        elif a["norm_text"] != b["norm_text"]:
            diffs.append({
                "type": "modified",
                "input": a["text"],
                "output": b["text"],
                "page": a["page"]
            })

    return diffs