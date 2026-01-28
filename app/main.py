from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.messages import router as messages_router
from app.api.routes.digest import router as digest_router
from app.api.routes.clusters import router as clusters_router
from app.api.routes.actions import router as actions_router
from app.api.routes.auth_google import router as auth_google_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.demo import router as demo_router


def _cors_allow_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        # ✅ dev default so localhost:3000 can always call the API
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="InboxSherpa API")

origins = _cors_allow_origins()
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
app.include_router(actions_router)
app.include_router(auth_google_router)
app.include_router(metrics_router)
app.include_router(demo_router)
