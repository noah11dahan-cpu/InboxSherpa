from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.gmail import modify_thread_labels, GmailError

router = APIRouter(prefix="/actions", tags=["actions"])


class ThreadLabelModifyIn(BaseModel):
    thread_id: str = Field(..., min_length=3)
    add_label_ids: list[str] = Field(default_factory=list)
    remove_label_ids: list[str] = Field(default_factory=list)


@router.post("/thread/labels")
async def apply_thread_labels(req: ThreadLabelModifyIn) -> dict:
    """
    Dev-only endpoint: calls Gmail threads.modify for a thread_id.

    You must supply a valid access token.
    Replace the placeholder token retrieval with your real token store.
    """
    access_token = ""  # TODO: load from your DB token store
    if not access_token:
        raise HTTPException(status_code=401, detail="Missing access token (wire DB token store).")

    try:
        out = await modify_thread_labels(
            access_token=access_token,
            thread_id=req.thread_id,
            add_label_ids=req.add_label_ids,
            remove_label_ids=req.remove_label_ids,
        )
        return {"ok": True, "gmail": out}
    except GmailError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
