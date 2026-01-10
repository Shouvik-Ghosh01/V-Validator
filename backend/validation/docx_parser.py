from docx import Document

def parse_docx(file_path: str) -> list[dict]:
    doc = Document(file_path)
    blocks = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        blocks.append({
            "type": "paragraph",
            "text": text
        })

    return blocks