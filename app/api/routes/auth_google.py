from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.db.crypto import encrypt_token
from app.models import Channel, Cluster, GmailToken, Message, Thread, User

router = APIRouter(prefix="/auth/google", tags=["auth"])

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise HTTPException(status_code=500, detail=f"Missing {name}")
    return v


def _pkce_verifier() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _scopes() -> str:
    raw = os.getenv("GOOGLE_OAUTH_SCOPES", "")
    scopes = [s.strip() for s in raw.split(",") if s.strip()]
    if not scopes:
        scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    return " ".join(scopes)


class GoogleStartOut(BaseModel):
    auth_url: str
    state: str
    code_verifier: str
    redirect_uri: str


@router.get("/start", response_model=GoogleStartOut)
async def google_start(
    user_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    client_id = _require_env("GOOGLE_CLIENT_ID")
    redirect_uri = _require_env("GOOGLE_REDIRECT_URI")
    scope = _scopes()

    user_exists = await session.scalar(select(User.id).where(User.id == user_id))
    if not user_exists:
        raise HTTPException(status_code=400, detail=f"User not found: {user_id}")

    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    state = secrets.token_urlsafe(24)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    qs = "&".join([f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items()])
    auth_url = f"{AUTH_URL}?{qs}"

    return GoogleStartOut(
        auth_url=auth_url,
        state=state,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
    )


class GoogleExchangeIn(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str
    user_id: str
    state: Optional[str] = None


@router.post("/exchange")
async def google_exchange(payload: GoogleExchangeIn, session: AsyncSession = Depends(get_session)):
    client_id = _require_env("GOOGLE_CLIENT_ID")
    client_secret = _require_env("GOOGLE_CLIENT_SECRET")

    user_exists = await session.scalar(select(User.id).where(User.id == payload.user_id))
    if not user_exists:
        raise HTTPException(status_code=400, detail=f"User not found: {payload.user_id}")

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": payload.code,
        "code_verifier": payload.code_verifier,
        "redirect_uri": payload.redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(TOKEN_URL, data=data)

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {resp.text}")

    tok = resp.json()
    access_token = tok.get("access_token")
    refresh_token = tok.get("refresh_token")
    expires_in = int(tok.get("expires_in", 0) or 0)
    scope_str = tok.get("scope", "")

    if not access_token:
        raise HTTPException(status_code=400, detail="No access_token returned")
    if not refresh_token:
        # If you ever get here: Google only returns refresh_token on first consent
        # or if prompt=consent was used and previous grant was revoked.
        raise HTTPException(status_code=400, detail="No refresh_token returned")

    expires_at_dt = None
    if expires_in:
        expires_at_dt = datetime.fromtimestamp(int(time.time()) + expires_in, tz=timezone.utc)

    scope_list = [s for s in scope_str.split(" ") if s.strip()] or None

    # 1) Upsert gmail_tokens for this user
    existing_tok = await session.scalar(select(GmailToken).where(GmailToken.user_id == payload.user_id))
    if existing_tok:
        existing_tok.access_token_enc = encrypt_token(access_token)
        existing_tok.refresh_token_enc = encrypt_token(refresh_token)
        existing_tok.scope = scope_list
        existing_tok.expires_at = expires_at_dt
    else:
        session.add(
            GmailToken(
                user_id=payload.user_id,
                access_token_enc=encrypt_token(access_token),
                refresh_token_enc=encrypt_token(refresh_token),
                scope=scope_list,
                expires_at=expires_at_dt,
            )
        )

    # 2) Delete demo/json messages + threads for this user
    await session.execute(
        delete(Message).where(Message.user_id == payload.user_id, Message.channel == Channel.json)
    )
    await session.execute(
        delete(Thread).where(Thread.user_id == payload.user_id, Thread.channel == Channel.json)
    )

    # 3) Delete clusters that are NOT backed by Gmail messages
    # (keeps any clusters that actually have gmail messages attached)
    await session.execute(
        delete(Cluster).where(
            Cluster.user_id == payload.user_id,
            ~exists(
                select(1).where(
                    Message.cluster_id == Cluster.id,
                    Message.user_id == payload.user_id,
                    Message.channel == Channel.gmail,
                )
            ),
        )
    )

    await session.commit()

    return {
        "ok": True,
        "scope": scope_str,
        "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
        "has_refresh_token": True,
    }
