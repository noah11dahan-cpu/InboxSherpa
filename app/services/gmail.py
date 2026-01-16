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
