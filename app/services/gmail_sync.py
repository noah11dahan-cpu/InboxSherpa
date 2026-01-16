from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crypto import decrypt_token, encrypt_token
from app.models import Channel, GmailToken, Message, MessageStatus, Thread

TOKEN_URL = "https://oauth2.googleapis.com/token"


def _b64url_decode(data: str) -> bytes:
    data = data.replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - len(data) % 4) % 4)
    return base64.b64decode(data + pad)


def _extract_headers(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers", []) or []:
        name = h.get("name")
        value = h.get("value")
        if name and value:
            out[name.lower()] = value
    return out


def _walk_parts(part: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [part]
    for p in part.get("parts", []) or []:
        parts.extend(_walk_parts(p))
    return parts


def _extract_bodies(msg: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    payload = msg.get("payload") or {}
    if not payload:
        return None, None

    text: Optional[str] = None
    html: Optional[str] = None

    for p in _walk_parts(payload):
        mime = (p.get("mimeType") or "").lower()
        body = p.get("body") or {}
        data = body.get("data")
        if not data:
            continue
        raw = _b64url_decode(data)
        try:
            decoded = raw.decode("utf-8", errors="replace")
        except Exception:
            decoded = None

        if not decoded:
            continue

        if mime == "text/plain" and text is None:
            text = decoded
        if mime == "text/html" and html is None:
            html = decoded

    return text, html


async def _refresh_access_token(session: AsyncSession, tok: GmailToken) -> str:
    refresh_token = decrypt_token(tok.refresh_token_enc)
    data = {
        "client_id": _env("GOOGLE_CLIENT_ID"),
        "client_secret": _env("GOOGLE_CLIENT_SECRET"),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(TOKEN_URL, data=data)
    if r.status_code >= 400:
        raise RuntimeError(f"refresh_token failed: {r.status_code} {r.text}")

    js = r.json()
    access_token = js.get("access_token")
    expires_in = int(js.get("expires_in", 0) or 0)
    if not access_token:
        raise RuntimeError("refresh_token returned no access_token")

    tok.access_token_enc = encrypt_token(access_token)
    if expires_in:
        tok.expires_at = datetime.fromtimestamp(int(datetime.now(tz=timezone.utc).timestamp()) + expires_in, tz=timezone.utc)

    await session.commit()
    return access_token


def _env(name: str) -> str:
    import os
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing {name}")
    return v


async def _get_access_token(session: AsyncSession, user_id) -> str:
    tok = await session.scalar(select(GmailToken).where(GmailToken.user_id == user_id))
    if not tok:
        raise RuntimeError("No Gmail token stored for user")

    # If expired (or missing expires_at), try refresh; otherwise decrypt current access token
    if tok.expires_at and tok.expires_at <= datetime.now(tz=timezone.utc):
        return await _refresh_access_token(session, tok)

    try:
        return decrypt_token(tok.access_token_enc)
    except Exception:
        return await _refresh_access_token(session, tok)


async def sync_gmail_inbox(
    session: AsyncSession,
    *,
    user_id,
    max_messages: int = 50,
) -> dict:
    access_token = await _get_access_token(session, user_id)
    headers = {"Authorization": f"Bearer {access_token}"}

    # List INBOX messages
    list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    params = {"labelIds": "INBOX", "maxResults": max_messages}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(list_url, headers=headers, params=params)

    if r.status_code >= 400:
        raise RuntimeError(f"gmail messages.list failed: {r.status_code} {r.text}")

    items = (r.json().get("messages") or [])
    inserted = 0
    deduped = 0

    for it in items:
        mid = it.get("id")
        if not mid:
            continue

        get_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}"
        async with httpx.AsyncClient(timeout=30) as client:
            rr = await client.get(get_url, headers=headers, params={"format": "full"})
        if rr.status_code >= 400:
            continue

        msg = rr.json()
        thread_external_id = msg.get("threadId")
        internal_ms = int(msg.get("internalDate", 0) or 0)
        ts = datetime.fromtimestamp(internal_ms / 1000.0, tz=timezone.utc) if internal_ms else datetime.now(tz=timezone.utc)

        payload = msg.get("payload") or {}
        hdrs = _extract_headers(payload)
        sender = hdrs.get("from", "") or ""
        subject = hdrs.get("subject", "") or ""
        snippet = msg.get("snippet")

        body_text, body_html = _extract_bodies(msg)
        labels = msg.get("labelIds")

        thread_id = None
        if thread_external_id:
            existing_thread = await session.scalar(
                select(Thread).where(
                    Thread.user_id == user_id,
                    Thread.channel == Channel.gmail,
                    Thread.external_id == thread_external_id,
                )
            )
            if existing_thread:
                thread_id = existing_thread.id
            else:
                t = Thread(
                    user_id=user_id,
                    channel=Channel.gmail,
                    external_id=thread_external_id,
                    subject=subject or None,
                    last_message_at=ts,
                )
                session.add(t)
                await session.flush()
                thread_id = t.id

        m = Message(
            user_id=user_id,
            thread_id=thread_id,
            cluster_id=None,
            channel=Channel.gmail,
            external_id=mid,
            thread_external_id=thread_external_id,
            timestamp=ts,
            sender=sender,
            subject=subject,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
            labels=labels,
            history_id=msg.get("historyId"),
            status=MessageStatus.inbox,
            raw_payload=msg,
        )

        tx = await session.begin_nested()
        try:
            session.add(m)
            await session.flush()
            await tx.commit()
            inserted += 1
        except IntegrityError:
            await tx.rollback()
            deduped += 1
        except Exception:
            await tx.rollback()

    await session.commit()
    return {"ok": True, "inserted": inserted, "deduped": deduped, "scanned": len(items)}