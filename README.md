# InboxSherpa

**AI-powered email triage that clusters your inbox and suggests actions.**

InboxSherpa syncs your Gmail, groups similar messages using machine learning, and proposes bulk actions (archive promos, snooze deadlines, apply labels) — giving you a daily digest instead of inbox chaos.

---

## Quick Start (One Command)

```bash
# Clone and run with Docker
git clone https://github.com/noah11dahan-cpu/InboxSherpa.git
cd InboxSherpa
cp .env.example .env
docker compose up --build
```

Then open:
- **API**: http://localhost:8001/health
- **Frontend**: http://localhost:3000

Click **"Try Demo"** on the home page to see it in action with sample data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                    │
│                         Next.js (React 19)                              │
│                         localhost:3000                                   │
│                                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐        │
│   │   Home   │    │  Digest  │    │ Cluster  │    │ Metrics  │        │
│   │  (OAuth) │───▶│  (List)  │───▶│ (Detail) │    │  (Stats) │        │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘        │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ HTTP/JSON
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                               BACKEND                                    │
│                        FastAPI (Python 3.11)                            │
│                          localhost:8001                                  │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐ │
│   │                         API Routes                                │ │
│   │  /auth/google/*  /digest/today  /clusters/{id}  /actions/apply   │ │
│   │  /messages/import  /metrics  /demo                               │ │
│   └──────────────────────────────────────────────────────────────────┘ │
│                             │                                           │
│   ┌─────────────────────────┴─────────────────────────────────────┐   │
│   │                        Services                                │   │
│   │                                                                │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │   │
│   │  │ gmail_sync  │  │ clustering  │  │ suggested_actions   │   │   │
│   │  │  (OAuth +   │  │ (TF-IDF +   │  │ (Rule-based         │   │   │
│   │  │  Gmail API) │  │  KMeans)    │  │  proposals)         │   │   │
│   │  └─────────────┘  └─────────────┘  └─────────────────────┘   │   │
│   │                                                                │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │   │
│   │  │ summarizer  │  │ action_rules│  │ importer            │   │   │
│   │  │ (Heuristic) │  │ (YAML)      │  │ (JSON→DB)           │   │   │
│   │  └─────────────┘  └─────────────┘  └─────────────────────┘   │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ asyncpg
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            DATABASE                                      │
│                      PostgreSQL 16 (Docker)                             │
│                          localhost:5432                                  │
│                                                                         │
│   ┌────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐           │
│   │ users  │  │messages │  │clusters │  │suggested_actions│           │
│   └────────┘  └─────────┘  └─────────┘  └─────────────────┘           │
│   ┌────────┐  ┌─────────┐  ┌─────────────────────────────┐           │
│   │threads │  │gmail_   │  │pipeline_runs (metrics)      │           │
│   │        │  │tokens   │  │                             │           │
│   └────────┘  └─────────┘  └─────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                             WORKER                                       │
│                    Background Gmail Sync Loop                           │
│                                                                         │
│   Runs continuously, syncing today's messages for all connected users  │
│   Configurable: SYNC_SLEEP_SECONDS, SYNC_TZ, SYNC_MAX_MESSAGES         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## How Clustering Works

InboxSherpa uses a **two-stage clustering approach**:

### Stage 1: Text Vectorization
- Combines message subject + body + snippet into a single text blob
- Applies **TF-IDF vectorization** (Term Frequency-Inverse Document Frequency)
- Uses English stop words, bigrams, and max 6,000 features

### Stage 2: Grouping
- **Small datasets (< 8 messages)**: Keyword-based bucketing into predefined categories (Promos, School, Bills, Work, Social)
- **Large datasets (≥ 8 messages)**: **KMeans clustering** with dynamic K selection
  - K = √n, clamped to [2, 12]
  - Cluster titles generated from top TF-IDF terms

### After Clustering
- **Summarizer** generates bullets from top senders, keywords, and urgency signals
- **Action Rules Engine** proposes actions based on YAML rules (configurable)
- Everything is stored per (user, digest_date) for daily digests

```
Messages → TF-IDF → KMeans → Clusters → Summarizer → Suggested Actions
                              │
                              └─→ "Promos (12 msgs)" → "Archive all"
                              └─→ "Bills (3 msgs)"   → "Snooze 24h"
```

---

## Data Flow

```
1. User connects Gmail via OAuth 2.0
   └─→ Tokens encrypted at rest (Fernet)

2. Worker syncs messages (background loop)
   └─→ Gmail API → PostgreSQL

3. User requests digest for a date
   └─→ Auto-sync if needed → Cluster → Summarize → Propose actions

4. User accepts/rejects actions
   └─→ Gmail labels modified → Local status updated
```

---

## Privacy & Security

InboxSherpa is designed with privacy in mind:

| Principle | Implementation |
|-----------|----------------|
| **No auto-archive** | Actions are *proposed*, never executed without explicit user approval |
| **Minimal scopes** | Gmail read-only + labels modify (no send, no delete) |
| **Encrypted tokens** | OAuth tokens encrypted at rest with Fernet (AES-128) |
| **Delete your data** | Full data deletion available (user + messages + tokens) |
| **Local-first option** | Can run entirely on localhost with Docker |
| **No third-party AI** | Clustering uses local scikit-learn, no data sent to external LLMs |

### OAuth Scopes Requested
```
gmail.readonly         - Read messages and labels
gmail.labels           - Create and modify labels
gmail.modify           - Modify message labels (archive, etc.)
userinfo.email         - Get user's email address
```

---

## Demo Mode

Click **"Try Demo"** on the home page to:
1. Create a demo user with sample inbox data (200+ messages)
2. Auto-redirect to the digest page
3. See clusters like "School", "Promos", "Calendar", "Bills"
4. Try accepting/rejecting suggested actions

No Gmail connection required for demo mode.

---

## Development

### Local Setup (without Docker)

```bash
# Backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Start Postgres (via Docker or local install)
docker compose up db -d

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

### Running Tests

```bash
# Requires Postgres running
pytest -q

# With coverage
pytest --cov=app --cov-report=term-missing
```

### Running Evals (AI Summary Quality)

```bash
python -m evals.run           # Run evaluation
python -m evals.run --verbose # Per-test details
```

### Linting

```bash
ruff check . --fix
cd web && npm run lint
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/demo` | POST | Start demo mode (imports sample data) |
| `/digest/today` | GET | Get digest with clusters for a date |
| `/clusters/{id}` | GET | Cluster detail with messages |
| `/actions/apply` | POST | Accept/reject suggested action |
| `/auth/google/start` | GET | Begin Gmail OAuth flow |
| `/auth/google/exchange` | POST | Exchange OAuth code for tokens |
| `/messages/import` | POST | Import JSON messages |
| `/metrics` | GET | User metrics and stats |

---

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/inboxsherpa

# Gmail OAuth (get from Google Cloud Console)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback

# Security
TOKEN_ENCRYPTION_KEY=base64-encoded-32-byte-key

# Optional
CORS_ALLOW_ORIGINS=http://localhost:3000
ACTION_RULES_PATH=data/action_rules.yaml
SYNC_TZ=America/Montreal
SYNC_MAX_MESSAGES=500
SYNC_SLEEP_SECONDS=60
```

---

## Roadmap

### Current (v0.1 - MVP)
- [x] Gmail OAuth integration
- [x] TF-IDF + KMeans clustering
- [x] Rule-based action suggestions
- [x] Accept/reject actions with Gmail sync
- [x] Background worker for continuous sync
- [x] Metrics and observability
- [x] Load testing (5k messages < 30s)
- [x] AI eval harness

### Future
- [ ] LLM-powered summarization (optional, privacy-preserving)
- [ ] Smart snooze with calendar awareness
- [ ] Multi-account support
- [ ] Mobile app (React Native)
- [ ] Browser extension for quick triage
- [ ] Custom clustering rules
- [ ] Export/backup functionality

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, asyncpg |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Database | PostgreSQL 16 |
| ML | scikit-learn (TF-IDF, KMeans) |
| Auth | Google OAuth 2.0 with PKCE |
| Infra | Docker Compose, Alembic migrations |

---

## License

MIT

---

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

```bash
# Fork, clone, branch
git checkout -b feature/your-feature

# Make changes, test
pytest -q
ruff check .

# Commit and PR
git commit -m "Add your feature"
git push origin feature/your-feature
```
