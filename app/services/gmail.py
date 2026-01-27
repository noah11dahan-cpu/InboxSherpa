from __future__ import annotations

from typing import Iterable, Optional

import httpx


class GmailError(RuntimeError):
    pass


async def modify_thread_labels(
    *,
    access_token: str,
    thread_id: str,
    add_label_ids: Optional[Iterable[str]] = None,
    remove_label_ids: Optional[Iterable[str]] = None,
) -> dict:
    """
    Applies labels at the THREAD level:
    POST https://gmail.googleapis.com/gmail/v1/users/me/threads/{id}/modify
    Body: {"addLabelIds":[...], "removeLabelIds":[...]}
    """
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/threads/{thread_id}/modify"
    payload: dict = {}
    if add_label_ids:
        payload["addLabelIds"] = list(add_label_ids)
    if remove_label_ids:
        payload["removeLabelIds"] = list(remove_label_ids)

    if not payload:
        return {"ok": True, "changed": False}

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload, headers=headers)

    if r.status_code >= 400:
        raise GmailError(f"Gmail threads.modify failed: {r.status_code} {r.text}")

    return r.json()


# -----------------------------
# Day 12 helpers (labels list/create/ensure)
# -----------------------------

async def list_labels(*, access_token: str) -> list[dict]:
    """
    GET https://gmail.googleapis.com/gmail/v1/users/me/labels
    Returns list of {"id": "...", "name": "...", ...}
    """
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers)

    if r.status_code >= 400:
        raise GmailError(f"Gmail labels.list failed: {r.status_code} {r.text}")

    js = r.json() or {}
    labels = js.get("labels") or []
    if not isinstance(labels, list):
        return []
    return [x for x in labels if isinstance(x, dict)]


async def create_label(
    *,
    access_token: str,
    name: str,
    label_list_visibility: str = "labelShow",
    message_list_visibility: str = "show",
) -> dict:
    """
    POST https://gmail.googleapis.com/gmail/v1/users/me/labels
    """
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "name": name,
        "labelListVisibility": label_list_visibility,
        "messageListVisibility": message_list_visibility,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload, headers=headers)

    if r.status_code >= 400:
        raise GmailError(f"Gmail labels.create failed: {r.status_code} {r.text}")

    return r.json()


async def ensure_label_id(*, access_token: str, label_name: str) -> str:
    """
    Finds (case-insensitive) label by name, else creates it.
    Returns label id.
    """
    name = (label_name or "").strip()
    if not name:
        raise GmailError("label_name is empty")

    labels = await list_labels(access_token=access_token)
    for label in labels:
        if (label.get("name") or "").strip().lower() == name.lower():
            lid = label.get("id")
            if isinstance(lid, str) and lid:
                return lid

    created = await create_label(access_token=access_token, name=name)
    lid = created.get("id")
    if not isinstance(lid, str) or not lid:
        raise GmailError("labels.create returned no id")
    return lid
