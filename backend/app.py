from pydantic import BaseModel
import tempfile
from fastapi import UploadFile, File
from backend.validation.service import compare_pdfs
import tempfile

from backend.agent.agent import run_agent
from backend.safety.input_guard import is_query_allowed
from backend.safety.prompt_guard import is_prompt_safe
from backend.validation.service import compare_documents

app = FastAPI()


# -----------------------------
# REQUEST MODELS
# -----------------------------
class AskRequest(BaseModel):
    query: str


# -----------------------------
# PIPELINE 1: INTERNAL RAG
# -----------------------------
@app.post("/ask")
def ask(req: AskRequest):
    query = req.query.strip()

    # Rule-based input validation
    if not is_query_allowed(query):
        return {
            "answer": "This query is outside the allowed scope.",
            "sources": [],
        }

    # Prompt injection / jailbreak detection
    if not is_prompt_safe(query):
        return {
            "answer": "Query blocked due to unsafe or malicious intent.",
            "sources": [],
        }

    return run_agent(query)


# -----------------------------
# PIPELINE 2: DOCX ↔ PDF COMPARISON
# -----------------------------
@app.post("/compare")
async def compare_documents(
    input_pdf: UploadFile = File(...),
    output_pdf: UploadFile = File(...)
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f1, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f2:

        f1.write(await input_pdf.read())
        f2.write(await output_pdf.read())

        result = compare_pdfs(f1.name, f2.name)

    return result