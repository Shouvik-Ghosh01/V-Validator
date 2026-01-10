from difflib import SequenceMatcher

def align_blocks(a_blocks, b_blocks, threshold=0.85):
    """
    Align blocks based on text similarity.
    """
    aligned = []

    for a in a_blocks:
        best = None
        best_score = 0

        for b in b_blocks:
            score = SequenceMatcher(
                None, a["norm_text"], b["norm_text"]
            ).ratio()

            if score > best_score:
                best_score = score
                best = b

        if best_score >= threshold:
            aligned.append((a, best, best_score))
        else:
            aligned.append((a, None, best_score))

    return aligned
