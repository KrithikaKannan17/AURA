# AURA - Automated Unified Response Architecture

A multi-agent RAG system that ingests runbooks (PDF/Markdown), converts them into executable incident workflows, and provides automated diagnosis with safe escalation logic.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│  Runbook Manager │ Incident Reporter │ Diagnosis Panel       │
│  Workflow Viewer │ Escalation Panel  │ Incident History      │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend                           │
│                                                              │
│  ┌─────────────────── LangGraph Pipeline ─────────────────┐ │
│  │                                                         │ │
│  │  ┌─────────────┐    ┌─────────────┐    ┌────────────┐  │ │
│  │  │  Ingestion  │    │  Diagnosis  │───▶│  Workflow  │  │ │
│  │  │    Agent    │    │    Agent    │    │   Agent    │  │ │
│  │  └─────────────┘    └──────┬──────┘    └─────┬──────┘  │ │
│  │                            │ RAG               │         │ │
│  │                     ┌──────▼──────┐    ┌──────▼──────┐  │ │
│  │                     │  ChromaDB   │    │ Escalation  │  │ │
│  │                     │  (vectors)  │    │    Agent    │  │ │
│  │                     └─────────────┘    └─────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  SQLite / PostgreSQL (incidents, runbooks, workflow steps)   │
└─────────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Responsibility |
|-------|---------------|
| **Ingestion Agent** | Parse PDF/MD → chunk (512/64) → embed → ChromaDB |
| **Diagnosis Agent** | RAG retrieval + LLM prompt → root cause + confidence score |
| **Workflow Agent** | Convert remediation steps → structured executable workflow with safety validation |
| **Escalation Agent** | Detect low confidence / P1 → generate report → POST to Slack/PagerDuty |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- `OPENAI_API_KEY` or `COHERE_API_KEY`

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
# Visit http://localhost:3000
```

### 4. Or use Docker Compose

```bash
docker compose up --build
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API docs: http://localhost:8000/docs
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/runbooks/upload` | Upload + embed runbook (PDF/MD) |
| `GET` | `/api/runbooks` | List all indexed runbooks |
| `DELETE` | `/api/runbooks/{id}` | Delete runbook and its embeddings |
| `POST` | `/api/incidents/diagnose` | Trigger full multi-agent pipeline |
| `GET` | `/api/incidents` | List all past incidents |
| `GET` | `/api/incidents/{id}` | Get incident detail with steps + escalation |
| `POST` | `/api/incidents/{id}/execute` | Start workflow execution |
| `POST` | `/api/incidents/{id}/confirm-step` | Confirm/reject a destructive step |
| `WS` | `/ws/incidents/{id}` | Stream real-time execution status |

### Diagnose an Incident

```bash
curl -X POST http://localhost:8000/api/incidents/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "PostgreSQL is refusing connections. App logs show: FATAL: remaining connection slots are reserved for non-replication superuser connections",
    "severity": "P1",
    "system_affected": "Database (PostgreSQL)"
  }'
```

### Upload a Runbook

```bash
curl -X POST http://localhost:8000/api/runbooks/upload \
  -F "file=@runbooks/database-outage-runbook.md"
```

---

## Folder Structure

```
aura/
├── frontend/                    # Next.js 16 app
│   ├── app/                     # App router
│   ├── components/
│   │   ├── panels/              # 5 main feature panels
│   │   └── ui/                  # Reusable UI primitives
│   ├── lib/                     # API client + utilities
│   └── types/                   # TypeScript type definitions
│
├── backend/
│   ├── main.py                  # FastAPI app + all endpoints
│   ├── graph.py                 # LangGraph pipeline wiring
│   ├── vector_store.py          # ChromaDB setup + retrieval
│   ├── models.py                # SQLAlchemy schemas
│   └── agents/
│       ├── ingestion_agent.py   # Parse → chunk → embed
│       ├── diagnosis_agent.py   # RAG + LLM diagnosis
│       ├── workflow_agent.py    # Remediation → executable workflow
│       └── escalation_agent.py # Escalation report + webhooks
│
├── runbooks/                    # 3 sample runbooks
│   ├── database-outage-runbook.md
│   ├── kubernetes-pod-crashloop-runbook.md
│   └── api-high-latency-runbook.md
│
├── docker-compose.yml
└── .env.example
```

---

## Safety Guardrails

The Workflow Agent automatically detects and flags destructive commands:

- `kubectl delete`, `kubectl drain`
- `DROP TABLE`, `TRUNCATE TABLE`, `DELETE FROM`
- `rm -rf`, `rm -f`
- `dd if=`, `mkfs.*`
- `shutdown`, `reboot`, `poweroff`

Flagged steps:
1. Are marked `requires_confirmation: true`
2. Pause execution with `awaiting_confirmation` status
3. Require explicit human approval via the UI or `/confirm-step` API
4. Are never auto-executed

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes (or Cohere) | GPT-4o for LLM + embeddings |
| `COHERE_API_KEY` | Yes (or OpenAI) | Alternative LLM + embeddings |
| `CHROMA_PERSIST_PATH` | No | Path to ChromaDB storage (default: `./chroma_data`) |
| `DATABASE_URL` | No | SQLAlchemy URL (default: SQLite) |
| `SLACK_WEBHOOK_URL` | No | Slack webhook for escalation (mock if not set) |
| `PAGERDUTY_ROUTING_KEY` | No | PagerDuty routing key (mock if not set) |
# AURA
