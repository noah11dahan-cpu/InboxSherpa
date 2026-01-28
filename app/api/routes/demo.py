"""
Demo mode endpoint - imports sample data for quick demonstration.

POST /demo creates a demo user and imports sample_inbox.json
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.models import User
from app.schemas.importer import ImportRequest
from app.services.importer import import_json_messages

router = APIRouter(tags=["demo"])

# Deterministic demo user ID (same as tests)
DEMO_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "demo@inboxsherpa.local")
DEMO_EMAIL = "demo@inboxsherpa.local"
SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sample_inbox.json"


class DemoResponse(BaseModel):
    """Response from demo endpoint."""
    user_id: str
    email: str
    messages_imported: int
    digest_date: str
    next_step: str


@router.post("/demo", response_model=DemoResponse)
async def start_demo(session: AsyncSession = Depends(get_session)) -> DemoResponse:
    """
    Start demo mode.

    Creates a demo user (if not exists) and imports sample inbox data.
    Returns user_id and instructions for next steps.
    """
    # Check if demo user exists
    result = await session.execute(select(User).where(User.id == DEMO_USER_ID))
    user = result.scalar_one_or_none()

    if not user:
        # Create demo user
        user = User(
            id=DEMO_USER_ID,
            email=DEMO_EMAIL,
            gmail_account_email=DEMO_EMAIL,
        )
        session.add(user)
        await session.commit()

    # Check if sample data file exists
    if not SAMPLE_DATA_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Sample data file not found: {SAMPLE_DATA_PATH}",
        )

    # Import sample messages
    import_req = ImportRequest(
        user_id=DEMO_USER_ID,
        file_path=str(SAMPLE_DATA_PATH),
    )

    try:
        result = await import_json_messages(session=session, req=import_req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Get today's date for the digest
    today = date.today().isoformat()

    return DemoResponse(
        user_id=str(DEMO_USER_ID),
        email=DEMO_EMAIL,
        messages_imported=result.inserted,
        digest_date=today,
        next_step=f"Visit /digest?user_id={DEMO_USER_ID} to see your demo digest",
    )
