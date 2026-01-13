from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import tempfile
import os

from backend.agent.agent import run_agent
from backend.safety.input_guard import is_query_allowed
from backend.safety.prompt_guard import is_prompt_safe
from backend.compare.service import compare_pdfs

app = FastAPI(title="Spotline Internal Platform")


# -----------------------------
# REQUEST MODELS
# -----------------------------
class AskRequest(BaseModel):
    query: str


# -----------------------------
# PIPELINE 1: INTERNAL RAG CHAT
# -----------------------------
@app.post("/ask")
def ask(req: AskRequest):
    query = req.query.strip()

    if not query:
        return {"answer": "Empty query.", "sources": []}

    # Rule-based input validation
    if not is_query_allowed(query):
        return {
            "answer": "This query is outside the allowed scope.",
            "sources": [],
        }

    #Prompt injection / jailbreak detection (fail-open)
    try:
        safe = is_prompt_safe(query)
    except Exception:
        safe = True

    if safe is False:
        return {
            "answer": "Query blocked due to unsafe or malicious intent.",
            "sources": [],
        }

    return run_agent(query)


# -----------------------------
# PIPELINE 2: PDF ↔ PDF VALIDATION
# -----------------------------
@app.post("/compare")
def compare(
    client_pdf: UploadFile = File(...),
    output_pdf: UploadFile = File(...),
):
    client_path = None
    output_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as c:
            c.write(client_pdf.file.read())
            client_path = c.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as o:
            o.write(output_pdf.file.read())
            output_path = o.name

        diffs = compare_pdfs(client_path, output_path)
        return {"differences": diffs}

    except Exception as e:
        # 👇 PRINT FULL ERROR TO CONSOLE
        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    finally:
        if client_path and os.path.exists(client_path):
            os.remove(client_path)
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
