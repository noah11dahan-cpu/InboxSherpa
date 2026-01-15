from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.messages import router as messages_router
from app.api.routes.digest import router as digest_router
from app.api.routes.clusters import router as clusters_router


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins


app = FastAPI(title="InboxSherpa API")

# CORS: configured by env var only (no hardcoding)
origins = _cors_allow_origins()
if origins:
    allow_all = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


app.include_router(messages_router)
app.include_router(digest_router)
app.include_router(clusters_router)
