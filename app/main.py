from fastapi import FastAPI
from app.api.routes.health import router as health_router
from app.api.routes.messages import router as messages_router

app = FastAPI(title="InboxSherpa API", version="0.1.0")

app.include_router(health_router)
app.include_router(messages_router)
