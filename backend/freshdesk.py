import os
import base64
from datetime import datetime
from io import BytesIO

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/freshdesk", tags=["freshdesk"])

FRESHDESK_DOMAIN = os.getenv("FRESHDESK_DOMAIN", "")
FRESHDESK_API_KEY = os.getenv("FRESHDESK_API_KEY", "")

TAG_LABELS = {
    "text_incorrect": "Text Incorrect",
    "screenshot_incorrect": "Screenshot Incorrect",
    "step_incorrect": "Step Incorrect",
    "other": "Other",
}

TAG_COLORS = {
    "text_incorrect": "#ef4444",
    "screenshot_incorrect": "#f59e0b",
    "step_incorrect": "#F5A623",
    "other": "#6b7280",
}


def _check_config():
    if not FRESHDESK_DOMAIN or not FRESHDESK_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Freshdesk not configured. Set FRESHDESK_DOMAIN and FRESHDESK_API_KEY environment variables.",
        )


def _fd_get(path: str, params: dict | None = None):
    _check_config()
    url = f"https://{FRESHDESK_DOMAIN}/api/v2/{path}"
    r = requests.get(url, params=params, auth=(FRESHDESK_API_KEY, "X"), timeout=10)
    r.raise_for_status()
    return r.json()


def _fd_post_multipart(path: str, data: dict, files: list):
    _check_config()
    url = f"https://{FRESHDESK_DOMAIN}/api/v2/{path}"
    r = requests.post(url, data=data, files=files, auth=(FRESHDESK_API_KEY, "X"), timeout=30)
    r.raise_for_status()
    return r.json()


@router.get("/search")
def search_ticket(release: str = Query(...), script_id: str = Query(...)):
    """Search Freshdesk for a ticket whose subject contains '<release> <script_id>'."""
    primary_query = f'subject:"{release} {script_id}"'
    results = []
    try:
        data = _fd_get("search/tickets", params={"query": primary_query})
        results = data.get("results", [])
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Freshdesk search failed: {e}")

    # Fallback: search by script ID alone
    if not results:
        try:
            data2 = _fd_get("search/tickets", params={"query": f'subject:"{script_id}"'})
            results = data2.get("results", [])
        except requests.HTTPError:
            pass

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No Freshdesk ticket found matching '{release} {script_id}'.",
        )

    ticket = results[0]
    assignee_name = None
    assignee_id = ticket.get("responder_id")
    if assignee_id:
        try:
            agent = _fd_get(f"agents/{assignee_id}")
            assignee_name = agent.get("contact", {}).get("name")
        except Exception:
            pass

    return {
        "ticket_id": ticket["id"],
        "subject": ticket.get("subject", ""),
        "status": ticket.get("status"),
        "assignee_id": assignee_id,
        "assignee_name": assignee_name,
        "total_results": len(results),
    }


class NoteEntrySchema(BaseModel):
    comment: str
    tag: str
    stepRef: str
    timestamp: str
    imageDataUrl: str | None = None


class PostReplyRequest(BaseModel):
    ticket_id: int
    notes: list[NoteEntrySchema]
    script_id: str
    release: str


def _build_html_body(notes: list[NoteEntrySchema], script_id: str, release: str) -> str:
    items_html = ""
    for i, n in enumerate(notes):
        label = TAG_LABELS.get(n.tag, n.tag)
        color = TAG_COLORS.get(n.tag, "#666")
        step_line = (
            f'<p style="margin:3px 0;font-size:12px;color:#555"><b>Step ref:</b> {n.stepRef}</p>'
            if n.stepRef else ""
        )
        comment_line = (
            f'<p style="margin:6px 0;font-size:13px;color:#222;white-space:pre-wrap">{n.comment}</p>'
            if n.comment else ""
        )
        img_note = (
            '<p style="margin:4px 0;font-size:11px;color:#888;font-style:italic">'
            f'[Screenshot attached — see attachment #{i + 1}]</p>'
            if n.imageDataUrl else ""
        )
        items_html += f"""
<div style="border:1px solid {color}44;border-radius:8px;padding:12px 14px;margin-bottom:12px;background:#fff">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
    <span style="font-size:11px;color:#999">#{i + 1}</span>
    <span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px;background:{color}1a;color:{color};border:1px solid {color}44">{label}</span>
  </div>
  {step_line}
  <p style="margin:2px 0;font-size:11px;color:#999"><b>Time:</b> {n.timestamp}</p>
  {comment_line}
  {img_note}
</div>"""

    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<div style="font-family:system-ui,sans-serif;max-width:680px;padding:16px">
  <h2 style="font-size:16px;font-weight:700;color:#F5A623;margin:0 0 4px">V-Assure Validation Notes</h2>
  <p style="font-size:12px;color:#666;margin:0 0 12px">
    Script: <b>{script_id}</b> &nbsp;|&nbsp; Release: <b>{release}</b> &nbsp;|&nbsp; Exported: {exported_at}
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin-bottom:16px">
  {items_html}
</div>"""


@router.post("/post-reply")
def post_reply(req: PostReplyRequest):
    """Post validation notes as a private note on a Freshdesk ticket, with screenshot attachments."""
    html_body = _build_html_body(req.notes, req.script_id, req.release)

    data = {"body": html_body, "private": "true"}
    files: list = []

    for i, note in enumerate(req.notes):
        if note.imageDataUrl and note.imageDataUrl.startswith("data:"):
            try:
                header, b64 = note.imageDataUrl.split(",", 1)
                ext = "jpg" if "jpeg" in header.lower() or "jpg" in header.lower() else "png"
                img_bytes = base64.b64decode(b64)
                label = TAG_LABELS.get(note.tag, note.tag)
                fname = f"note-{i + 1}-{label.lower().replace(' ', '-')}.{ext}"
                files.append(("attachments[]", (fname, BytesIO(img_bytes), f"image/{ext}")))
            except Exception:
                pass  # skip malformed image

    try:
        result = _fd_post_multipart(f"tickets/{req.ticket_id}/notes", data=data, files=files)
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else str(e)
        raise HTTPException(status_code=502, detail=f"Freshdesk API error: {body}")

    return {"success": True, "note_id": result.get("id")}
