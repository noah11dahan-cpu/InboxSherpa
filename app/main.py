from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.messages import router as messages_router
from app.api.routes.digest import router as digest_router

app = FastAPI(title="InboxSherpa API")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}



app.include_router(messages_router)
app.include_router(digest_router)
