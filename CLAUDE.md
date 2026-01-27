# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InboxSherpa is an AI-first email triage application that syncs Gmail messages, clusters them into meaningful groups, and suggests actions. It consists of:
- **Python/FastAPI backend** (`app/`) with PostgreSQL
- **Next.js frontend** (`web/`)
- **Background worker** (`workers/`) for Gmail sync

## Common Commands

### Backend (Python)
```bash
# Local development (requires .env with DATABASE_URL)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests (uses pytest-asyncio, auto seeds demo user)
pytest -q

# Run single test file
pytest tests/test_health.py -v

# Lint/format
ruff check . --fix

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (Next.js)
```bash
cd web
npm run dev    # http://localhost:3000
npm run build
npm run lint
```

### Docker (full stack)
```bash
docker compose up --build     # API on :8001, Postgres on :5432
docker compose down -v        # Remove volumes
```

## Architecture

### Data Flow
1. **Gmail OAuth** (`app/api/routes/auth_google.py`) stores encrypted tokens in `gmail_tokens` table
2. **Gmail Sync** (`app/services/gmail_sync.py`) fetches messages for a specific date range using Gmail API
3. **Clustering** (`app/services/clustering.py`) uses TF-IDF + KMeans (scikit-learn) to group messages by content similarity
4. **Suggested Actions** (`app/services/action_rules.py`, `app/services/suggested_actions.py`) proposes actions like archive, label, snooze based on cluster content
5. **Digest API** (`app/api/routes/digest.py`) orchestrates sync + clustering + action proposals on demand

### Key Models (`app/models.py`)
- `User` - 1:1 with Gmail account
- `Message` - Gmail messages with body, labels, status (inbox/archived/snoozed/deleted)
- `Thread` - Gmail thread grouping
- `Cluster` - ML-generated message groups per (user, digest_date)
- `SuggestedAction` - Proposed actions with urgency/confidence
- `GmailToken` - Encrypted OAuth tokens
- `PipelineRun` - Metrics for sync/clustering operations

### Database
- PostgreSQL 16 with async SQLAlchemy (`asyncpg`)
- Alembic migrations in `alembic/versions/`
- Timezone-aware: clustering interprets `digest_date` in "America/Montreal" timezone

### Workers
- `workers/gmail_sync_worker.py` - Continuous loop syncing today's messages for all users
- Configured via `SYNC_SLEEP_SECONDS`, `SYNC_TZ`, `SYNC_MAX_MESSAGES` env vars

### Testing
- Tests require running Postgres (use `docker compose up db` or local)
- `tests/conftest.py` auto-seeds a demo user (`demo@inboxsherpa.local`) with sample messages
- Test user ID is deterministic: `uuid.uuid5(uuid.NAMESPACE_DNS, "demo@inboxsherpa.local")`

## API Endpoints

- `GET /health` - Health check
- `POST /messages/import` - Import JSON messages (demo data)
- `GET /digest/today` - Get today's digest with clusters (auto-syncs Gmail, auto-clusters)
- `GET /clusters/{id}` - Cluster detail with messages and suggested actions
- `POST /actions/suggested/{id}/accept` or `/reject` - Accept/reject suggested actions
- `GET /auth/google/start` - Begin OAuth flow
- `GET /auth/google/callback` - OAuth callback
- `GET /metrics` - User metrics and pipeline run stats

## Environment Variables

Copy `.env.example` to `.env`. Key variables:
- `DATABASE_URL` - PostgreSQL connection string (asyncpg driver)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` - OAuth credentials
- `TOKEN_ENC_KEY` - Fernet key for encrypting Gmail tokens at rest
- `CORS_ALLOW_ORIGINS` - Allowed origins for frontend (default: localhost:3000)
- `ACTION_RULES_PATH` - Path to YAML file with rule-based action suggestions (default: `data/action_rules.yaml`)
