"""
AURA FastAPI Backend
Provides REST endpoints and WebSocket streaming for the multi-agent RAG system.
"""
import asyncio
import json
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    Depends, FastAPI, File, HTTPException, UploadFile, WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Load environment variables first
load_dotenv()

from graph import run_diagnosis_pipeline, run_ingestion
from models import (
    EscalationStatusEnum, Incident, IncidentStatusEnum, Runbook,
    SeverityEnum, WorkflowStep, create_tables, get_engine, get_session_factory,
    Escalation, StepStatusEnum,
)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("aura.api")

# ── DB setup ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aura.db")
engine = get_engine(DATABASE_URL)
SessionLocal = get_session_factory(engine)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".md"}


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AURA backend starting — creating database tables...")
    create_tables(engine)
    yield
    logger.info("AURA backend shutting down.")


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AURA — Automated Unified Response Architecture",
    description="Multi-agent RAG system for incident diagnosis and automated remediation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── DB dependency ──────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    incident_description: str = Field(..., min_length=10)
    severity: str = Field(..., pattern="^(P1|P2|P3)$")
    system_affected: str = Field(..., min_length=1)
    title: str | None = None


class StepConfirmRequest(BaseModel):
    step_id: int
    confirmed: bool


# ── WebSocket connection manager ───────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, incident_id: int, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(incident_id, []).append(ws)
        logger.info("WS connected for incident %d", incident_id)

    def disconnect(self, incident_id: int, ws: WebSocket):
        conns = self._connections.get(incident_id, [])
        if ws in conns:
            conns.remove(ws)
        logger.info("WS disconnected for incident %d", incident_id)

    async def broadcast(self, incident_id: int, data: dict):
        conns = self._connections.get(incident_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(incident_id, ws)


manager = ConnectionManager()


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_incident_or_404(incident_id: int, db: Session) -> Incident:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


# ══════════════════════════════════════════════════════════════════════════════
# RUNBOOK ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/runbooks/upload", tags=["Runbooks"])
async def upload_runbook(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a PDF or Markdown runbook, parse it, and embed chunks into ChromaDB."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Save file
    unique_name = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / unique_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Create DB record
    runbook = Runbook(
        filename=unique_name,
        original_filename=file.filename,
        file_type=suffix.lstrip("."),
        file_path=str(dest),
        status="processing",
    )
    db.add(runbook)
    db.commit()
    db.refresh(runbook)

    # Run ingestion pipeline (sync in background task for responsiveness)
    try:
        result = run_ingestion(
            file_path=str(dest),
            original_filename=file.filename,
            file_type=suffix.lstrip("."),
            runbook_id=runbook.id,
        )
        runbook.status = result["status"]
        runbook.chunk_count = result["chunk_count"]
        if result.get("error"):
            runbook.error_message = result["error"]
        db.commit()
        db.refresh(runbook)

        logger.info("Runbook %d indexed: %d chunks", runbook.id, runbook.chunk_count)
        return {
            "success": True,
            "runbook": runbook.to_dict(),
            "message": f"Successfully indexed {runbook.chunk_count} chunks.",
        }
    except Exception as exc:
        runbook.status = "failed"
        runbook.error_message = str(exc)
        db.commit()
        logger.exception("Runbook ingestion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runbooks", tags=["Runbooks"])
def list_runbooks(db: Session = Depends(get_db)):
    """List all indexed runbooks."""
    runbooks = db.query(Runbook).order_by(Runbook.created_at.desc()).all()
    return {"runbooks": [r.to_dict() for r in runbooks], "total": len(runbooks)}


@app.delete("/api/runbooks/{runbook_id}", tags=["Runbooks"])
def delete_runbook(runbook_id: int, db: Session = Depends(get_db)):
    """Delete a runbook from DB and remove its ChromaDB embeddings."""
    runbook = db.query(Runbook).filter(Runbook.id == runbook_id).first()
    if not runbook:
        raise HTTPException(status_code=404, detail="Runbook not found")

    from vector_store import delete_by_source
    delete_by_source(runbook.original_filename)

    try:
        Path(runbook.file_path).unlink(missing_ok=True)
    except Exception:
        pass

    db.delete(runbook)
    db.commit()
    return {"success": True, "message": f"Runbook {runbook_id} deleted."}


# ══════════════════════════════════════════════════════════════════════════════
# INCIDENT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/incidents/diagnose", tags=["Incidents"])
async def diagnose_incident(
    request: DiagnoseRequest,
    db: Session = Depends(get_db),
):
    """
    Trigger the full multi-agent pipeline:
    Diagnosis → Workflow Generation → Escalation (if needed)
    """
    title = request.title or request.incident_description[:80]

    # Create incident record
    incident = Incident(
        title=title,
        description=request.incident_description,
        severity=SeverityEnum(request.severity),
        system_affected=request.system_affected,
        status=IncidentStatusEnum.DIAGNOSING,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    try:
        # Run the LangGraph pipeline
        result = await run_diagnosis_pipeline(
            incident_id=incident.id,
            description=request.incident_description,
            severity=request.severity,
            system_affected=request.system_affected,
        )

        # Persist diagnosis results
        incident.root_cause = result.get("root_cause")
        incident.confidence_score = result.get("confidence_score")
        incident.remediation_steps = result.get("remediation_steps", [])
        incident.sources = result.get("sources", [])

        # Persist workflow steps
        workflow = result.get("workflow", [])
        for step_data in workflow:
            step = WorkflowStep(
                incident_id=incident.id,
                step_id=step_data.get("step_id", 0),
                action=step_data.get("action", ""),
                command=step_data.get("command"),
                expected_outcome=step_data.get("expected_outcome"),
                rollback=step_data.get("rollback"),
                is_destructive=1 if step_data.get("is_destructive") else 0,
                requires_confirmation=1 if step_data.get("requires_confirmation") else 0,
                status=StepStatusEnum.PENDING,
            )
            db.add(step)

        # Persist escalation if triggered
        if result.get("needs_escalation") and result.get("escalation_report"):
            esc = Escalation(
                incident_id=incident.id,
                reason=result.get("escalation_reason", "unknown"),
                summary=result.get("escalation_report", {}).get("incident_summary"),
                failure_reason=result.get("escalation_report", {}).get("failure_reason"),
                recommended_action=result.get("escalation_report", {}).get("recommended_on_call_action"),
                slack_status=EscalationStatusEnum(result.get("slack_status", "pending")),
                pagerduty_status=EscalationStatusEnum(result.get("pagerduty_status", "pending")),
                slack_response=result.get("slack_response"),
                pagerduty_response=result.get("pagerduty_response"),
            )
            db.add(esc)
            incident.status = IncidentStatusEnum.ESCALATED
        else:
            incident.status = IncidentStatusEnum.WORKFLOW_READY

        db.commit()
        db.refresh(incident)

        # Build response
        steps = db.query(WorkflowStep).filter(WorkflowStep.incident_id == incident.id).all()
        esc_record = db.query(Escalation).filter(Escalation.incident_id == incident.id).first()

        return {
            "success": True,
            "incident": incident.to_dict(),
            "workflow_steps": [s.to_dict() for s in steps],
            "escalation": esc_record.to_dict() if esc_record else None,
        }

    except Exception as exc:
        incident.status = IncidentStatusEnum.FAILED
        db.commit()
        logger.exception("Diagnosis pipeline failed for incident %d: %s", incident.id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/incidents", tags=["Incidents"])
def list_incidents(db: Session = Depends(get_db)):
    """List all past incidents."""
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).all()
    return {"incidents": [i.to_dict() for i in incidents], "total": len(incidents)}


@app.get("/api/incidents/{incident_id}", tags=["Incidents"])
def get_incident(incident_id: int, db: Session = Depends(get_db)):
    """Get a single incident with its workflow steps and escalation."""
    incident = _get_incident_or_404(incident_id, db)
    steps = db.query(WorkflowStep).filter(WorkflowStep.incident_id == incident_id).order_by(WorkflowStep.step_id).all()
    esc = db.query(Escalation).filter(Escalation.incident_id == incident_id).first()
    return {
        "incident": incident.to_dict(),
        "workflow_steps": [s.to_dict() for s in steps],
        "escalation": esc.to_dict() if esc else None,
    }


@app.post("/api/incidents/{incident_id}/execute", tags=["Incidents"])
async def execute_workflow(
    incident_id: int,
    db: Session = Depends(get_db),
):
    """
    Start streaming execution of the incident's workflow.
    Status updates are pushed via WebSocket /ws/incidents/{id}.
    This endpoint kicks off the async execution task.
    """
    incident = _get_incident_or_404(incident_id, db)

    if incident.status not in (IncidentStatusEnum.WORKFLOW_READY, IncidentStatusEnum.ESCALATED):
        raise HTTPException(
            status_code=400,
            detail=f"Incident is in status '{incident.status.value}' — cannot execute.",
        )

    steps = (
        db.query(WorkflowStep)
        .filter(WorkflowStep.incident_id == incident_id)
        .order_by(WorkflowStep.step_id)
        .all()
    )
    if not steps:
        raise HTTPException(status_code=400, detail="No workflow steps found.")

    incident.status = IncidentStatusEnum.EXECUTING
    incident.execution_started_at = datetime.utcnow()
    db.commit()

    # Launch async execution in background
    asyncio.create_task(_execute_steps(incident_id, steps, db))

    return {
        "success": True,
        "message": "Workflow execution started. Connect to WS for live updates.",
        "websocket_url": f"/ws/incidents/{incident_id}",
    }


async def _execute_steps(incident_id: int, steps: list[WorkflowStep], db: Session):
    """Background task: execute workflow steps sequentially, streaming via WS."""
    from agents.workflow_agent import simulate_step_execution

    db_session = SessionLocal()
    try:
        for step in steps:
            step_record = db_session.query(WorkflowStep).filter(WorkflowStep.id == step.id).first()
            if not step_record:
                continue

            if step_record.requires_confirmation:
                step_record.status = StepStatusEnum.AWAITING_CONFIRMATION
                db_session.commit()
                await manager.broadcast(incident_id, {
                    "type": "step_update",
                    "step_id": step_record.step_id,
                    "status": "awaiting_confirmation",
                    "message": f"Step {step_record.step_id} requires human confirmation: {step_record.command}",
                })
                # Wait up to 60s for confirmation via a separate API call
                for _ in range(60):
                    await asyncio.sleep(1)
                    db_session.refresh(step_record)
                    if step_record.status != StepStatusEnum.AWAITING_CONFIRMATION:
                        break
                else:
                    step_record.status = StepStatusEnum.SKIPPED
                    db_session.commit()
                    await manager.broadcast(incident_id, {
                        "type": "step_update",
                        "step_id": step_record.step_id,
                        "status": "skipped",
                        "message": "Timed out waiting for confirmation — step skipped.",
                    })
                    continue

            step_record.status = StepStatusEnum.RUNNING
            step_record.started_at = datetime.utcnow()
            db_session.commit()

            async for update in simulate_step_execution(step_record.to_dict()):
                await manager.broadcast(incident_id, {"type": "step_update", **update})

            step_record.status = StepStatusEnum.DONE
            step_record.completed_at = datetime.utcnow()
            db_session.commit()

        # Mark incident resolved
        incident = db_session.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = IncidentStatusEnum.RESOLVED
            incident.execution_completed_at = datetime.utcnow()
            db_session.commit()

        await manager.broadcast(incident_id, {
            "type": "execution_complete",
            "incident_id": incident_id,
            "status": "resolved",
            "message": "All workflow steps completed.",
        })

    except Exception as exc:
        logger.exception("Workflow execution failed for incident %d: %s", incident_id, exc)
        await manager.broadcast(incident_id, {
            "type": "error",
            "incident_id": incident_id,
            "message": f"Execution error: {exc}",
        })
    finally:
        db_session.close()


@app.post("/api/incidents/{incident_id}/confirm-step", tags=["Incidents"])
async def confirm_step(
    incident_id: int,
    body: StepConfirmRequest,
    db: Session = Depends(get_db),
):
    """Confirm or reject a step that requires human confirmation."""
    step = (
        db.query(WorkflowStep)
        .filter(
            WorkflowStep.incident_id == incident_id,
            WorkflowStep.step_id == body.step_id,
        )
        .first()
    )
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if body.confirmed:
        step.status = StepStatusEnum.PENDING
    else:
        step.status = StepStatusEnum.SKIPPED
    db.commit()

    return {"success": True, "step_id": body.step_id, "confirmed": body.confirmed}


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET
# ══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/incidents/{incident_id}")
async def websocket_incident(incident_id: int, websocket: WebSocket):
    """Stream real-time execution status updates for an incident workflow."""
    await manager.connect(incident_id, websocket)
    try:
        # Send current step statuses on connect
        db = SessionLocal()
        try:
            steps = (
                db.query(WorkflowStep)
                .filter(WorkflowStep.incident_id == incident_id)
                .order_by(WorkflowStep.step_id)
                .all()
            )
            await websocket.send_text(json.dumps({
                "type": "initial_state",
                "steps": [s.to_dict() for s in steps],
            }))
        finally:
            db.close()

        while True:
            # Keep connection alive; client can send ping messages
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        manager.disconnect(incident_id, websocket)
    except Exception as exc:
        logger.error("WebSocket error for incident %d: %s", incident_id, exc)
        manager.disconnect(incident_id, websocket)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": "AURA", "version": "1.0.0"}
