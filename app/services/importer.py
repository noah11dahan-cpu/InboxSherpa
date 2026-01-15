from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Message, MessageStatus, Thread, User
from app.schemas.importer import ImportRequest, ImportResult, NormalizedJsonMessage


def _load_messages_from_req(req: ImportRequest) -> list[dict[str, Any]]:
    if req.messages is not None:
        return req.messages

    if req.file_path and req.allow_file_path:
        path = req.file_path

        # Normalize Windows backslashes to be safe
        path = path.replace("\\", "/")

        # If caller sends relative path, resolve relative to current working directory
        # (works locally). In Docker, /app is WORKDIR so "data/..." also works.
        if not path.startswith("/"):
            # Keep as relative; open() will resolve from cwd
            pass

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return data["messages"]

        raise ValueError("JSON file must be a list OR an object with key 'messages' as a list.")

    raise ValueError("Provide either `messages` or `file_path`.")


async def _get_or_create_thread(
    session: AsyncSession,
    user_id,
    thread_external_id: str,
    subject: str | None,
) -> Thread:
    existing = await session.scalar(
        select(Thread).where(
            Thread.user_id == user_id,
            Thread.channel == Channel.json,
            Thread.external_id == thread_external_id,
        )
    )
    if existing:
        return existing

    tx = await session.begin_nested()
    try:
        t = Thread(
            user_id=user_id,
            channel=Channel.json,
            external_id=thread_external_id,
            subject=subject,
            last_message_at=None,
        )
        session.add(t)
        await session.flush()
        await tx.commit()
        return t
    except IntegrityError:
        await tx.rollback()

    existing2 = await session.scalar(
        select(Thread).where(
            Thread.user_id == user_id,
            Thread.channel == Channel.json,
            Thread.external_id == thread_external_id,
        )
    )
    if not existing2:
        raise RuntimeError("Thread insert failed unexpectedly.")
    return existing2


@asynccontextmanager
async def _maybe_begin(session: AsyncSession):
    # If caller already started a transaction, don't start another one.
    if session.in_transaction():
        yield
    else:
        async with session.begin():
            yield


async def import_json_messages(session: AsyncSession, req: ImportRequest) -> ImportResult:
    raw_items = _load_messages_from_req(req)

    received = len(raw_items)
    inserted = 0
    deduped = 0
    errors = 0

    # IMPORTANT: be safe if caller already has an open transaction
    async with _maybe_begin(session):
        user_exists = (await session.scalar(select(User.id).where(User.id == req.user_id))) is not None
        if not user_exists:
            raise ValueError(f"User not found for user_id={req.user_id}.")

        for raw in raw_items:
            try:
                m = NormalizedJsonMessage.model_validate(raw)
            except ValidationError:
                errors += 1
                continue

            thread_id = None
            if m.thread_external_id:
                t = await _get_or_create_thread(
                    session=session,
                    user_id=req.user_id,
                    thread_external_id=m.thread_external_id,
                    subject=m.subject,
                )
                thread_id = t.id

            msg = Message(
                user_id=req.user_id,
                thread_id=thread_id,
                cluster_id=None,
                channel=Channel.json,
                external_id=m.external_id,
                thread_external_id=m.thread_external_id,
                timestamp=m.timestamp,
                sender=m.sender,
                subject=m.subject,
                snippet=m.snippet,
                body_text=m.body_text,
                body_html=m.body_html,
                labels=m.labels,
                history_id=None,
                status=MessageStatus.inbox,
                raw_payload=m.raw_payload,
            )

            tx = await session.begin_nested()
            try:
                session.add(msg)
                await session.flush()
                await tx.commit()
                inserted += 1
            except IntegrityError:
                await tx.rollback()
                deduped += 1
            except Exception:
                await tx.rollback()
                errors += 1

    return ImportResult(
        user_id=req.user_id,
        received=received,
        inserted=inserted,
        deduped=deduped,
        errors=errors,
    )
