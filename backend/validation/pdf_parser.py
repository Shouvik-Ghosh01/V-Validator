import pdfplumber

def extract_pdf_blocks(pdf_path: str) -> list[dict]:
    """
    Extracts layout-aware text blocks from a PDF.
    """
    blocks = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
                use_text_flow=True,
                keep_blank_chars=True
            )

            for w in words:
                blocks.append({
                    "page": page_num,
                    "text": w["text"].strip(),
                    "x0": w["x0"],
                    "x1": w["x1"],
                    "top": w["top"],
                    "bottom": w["bottom"],
                })

    return blocks
