import logging
import os
import tempfile
from typing import Annotated, List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router, get_current_user, UserInfo
from compare.schemas import ComparisonMode
from compare.service import compare_pdfs

logger = logging.getLogger("vassure.api")

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

# ── Auth routes ───────────────────────────────────────────────────────────────
app.include_router(auth_router)


# ── Helpers ───────────────────────────────────────────────────────────────────

# Human-readable names for the two upload slots, per mode. Used only in error text.
_SLOT_LABELS = {
    ComparisonMode.TEMPLATE_VS_OUTPUT: ("Template PDF", "Output PDF"),
    ComparisonMode.OUTPUT_VS_OUTPUT: ("Output PDF A", "Output PDF B"),
}


def _parse_mode(raw: str) -> ComparisonMode:
    try:
        return ComparisonMode(raw)
    except ValueError:
        allowed = ", ".join(m.value for m in ComparisonMode)
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported comparison_mode. Allowed values: {allowed}",
        )


def _write_temp_pdf(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(data)
        return f.name


def _redact(message: str, paths: List[str]) -> str:
    """Never let server temp-file paths reach the client."""
    for p in paths:
        if p:
            message = message.replace(p, "<uploaded PDF>")
    return message


# ── /compare ──────────────────────────────────────────────────────────────────
@app.post("/compare")
async def compare(
    # Original field names — still accepted, exactly as before.
    client_pdf: Optional[UploadFile] = File(None),
    output_pdf: Optional[UploadFile] = File(None),
    # Mode-neutral names. pdf_a / pdf_b take precedence when both forms are sent.
    pdf_a: Optional[UploadFile] = File(None),
    pdf_b: Optional[UploadFile] = File(None),
    # Omitted => template_vs_output, so existing clients behave exactly as before.
    comparison_mode: Annotated[str, Form()] = ComparisonMode.TEMPLATE_VS_OUTPUT.value,
    current_user: Annotated[UserInfo, Depends(get_current_user)] = None,
):
    mode = _parse_mode(comparison_mode)
    label_a, label_b = _SLOT_LABELS[mode]

    first = pdf_a or client_pdf
    second = pdf_b or output_pdf
    if first is None or second is None:
        raise HTTPException(
            status_code=422,
            detail=f"Both {label_a} and {label_b} are required for {mode.value}.",
        )

    temp_paths: List[str] = []

    try:
        first_bytes = await first.read()
        second_bytes = await second.read()

        for label, data in ((label_a, first_bytes), (label_b, second_bytes)):
            if b"%PDF" not in data[:1024]:
                raise HTTPException(status_code=400, detail=f"{label} is not a valid PDF file.")

        first_tmp = _write_temp_pdf(first_bytes)
        temp_paths.append(first_tmp)
        second_tmp = _write_temp_pdf(second_bytes)
        temp_paths.append(second_tmp)

        logger.info("compare requested | mode=%s", mode.value)

        # compare_pdfs is synchronous and CPU-bound; keep it off the event loop.
        return await run_in_threadpool(compare_pdfs, first_tmp, second_tmp, mode)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Error in /compare (mode=%s)", mode.value)
        raise HTTPException(status_code=500, detail=_redact(str(e), temp_paths))

    finally:
        for p in temp_paths:
            if os.path.exists(p):
                os.unlink(p)
