
# InboxSherpa

Day 1 scaffold: FastAPI + Postgres + no-op worker via Docker Compose.

## Run (Docker)
1) Copy .env.example to .env
2) docker compose up --build
3) GET http://localhost:8000/health

## Run (Local venv)
1) python -m venv .venv
2) .\.venv\Scripts\Activate.ps1
3) pip install -r requirements.txt
4) uvicorn app.main:app --reload

