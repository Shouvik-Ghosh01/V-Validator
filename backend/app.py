import os
import tempfile
from typing import Annotated

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auth import router as auth_router, get_current_user, UserInfo
from backend.database import seed_admin_user
from backend.compare.service import compare_pdfs
from backend.agent.agent import run_agent
from backend.safety.input_guard import is_query_allowed
from backend.safety.prompt_guard import is_prompt_safe

app = FastAPI(title="V-Assure Internal API")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8081",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    seed_admin_user()

# ── Auth routes ───────────────────────────────────────────────────────────────
app.include_router(auth_router)


# ── /compare ──────────────────────────────────────────────────────────────────
@app.post("/compare")
async def compare(
    client_pdf: UploadFile = File(...),
    output_pdf: UploadFile = File(...),
    current_user: Annotated[UserInfo, Depends(get_current_user)] = None,
):
    client_tmp = None
    output_tmp = None

    try:
        # ✅ Proper async read
        client_bytes = await client_pdf.read()
        output_bytes = await output_pdf.read()

        # Write client PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(client_bytes)
            client_tmp = f.name

        # Write executed PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
            f.write(output_bytes)
            output_tmp = f.name

        print(f"📄 Client file saved: {client_tmp}")
        print(f"📄 Output file saved: {output_tmp}")

        # Run comparison
        result = compare_pdfs(client_tmp, output_tmp)

        return result

    except Exception as e:
        print("❌ ERROR in /compare:")
        import traceback
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup
        if client_tmp and os.path.exists(client_tmp):
            os.unlink(client_tmp)
        if output_tmp and os.path.exists(output_tmp):
            os.unlink(output_tmp)


# ── /ask ──────────────────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    query: str


@app.post("/ask")
def ask(
    req: AskRequest,
    current_user: Annotated[UserInfo, Depends(get_current_user)] = None,
):
    if not is_query_allowed(req.query):
        return {"answer": "This query is outside the allowed scope.", "sources": []}
    if is_prompt_safe(req.query):
        return {"answer": "Query blocked due to unsafe intent.", "sources": []}
    return run_agent(req.query)