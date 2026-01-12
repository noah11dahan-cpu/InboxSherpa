from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_session
from app.schemas.importer import ImportRequest, ImportResult
from app.services.importer import import_json_messages

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("/import", response_model=ImportResult)
async def import_messages(req: ImportRequest, session: AsyncSession = Depends(get_session)) -> ImportResult:
    try:
        return await import_json_messages(session=session, req=req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
