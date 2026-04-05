from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Enum,
    create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────

class SeverityEnum(str, PyEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class IncidentStatusEnum(str, PyEnum):
    OPEN = "open"
    DIAGNOSING = "diagnosing"
    WORKFLOW_READY = "workflow_ready"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"


class StepStatusEnum(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class EscalationStatusEnum(str, PyEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


# ── Models ─────────────────────────────────────────────────────────────────────

class Runbook(Base):
    __tablename__ = "runbooks"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf | md
    file_path = Column(String(512), nullable=False)
    chunk_count = Column(Integer, default=0)
    collection_name = Column(String(255), nullable=True)
    status = Column(String(50), default="processing")  # processing | indexed | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "chunk_count": self.chunk_count,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(Enum(SeverityEnum), nullable=False)
    system_affected = Column(String(255), nullable=False)
    status = Column(Enum(IncidentStatusEnum), default=IncidentStatusEnum.OPEN)

    # Diagnosis results
    root_cause = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    remediation_steps = Column(JSON, nullable=True)   # list[str]
    sources = Column(JSON, nullable=True)              # list[{source, section, page}]
    diagnosis_metadata = Column(JSON, nullable=True)

    # Execution tracking
    current_step = Column(Integer, default=0)
    execution_started_at = Column(DateTime(timezone=True), nullable=True)
    execution_completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    workflow_steps = relationship("WorkflowStep", back_populates="incident", cascade="all, delete-orphan")
    escalation = relationship("Escalation", back_populates="incident", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value if self.severity else None,
            "system_affected": self.system_affected,
            "status": self.status.value if self.status else None,
            "root_cause": self.root_cause,
            "confidence_score": self.confidence_score,
            "remediation_steps": self.remediation_steps,
            "sources": self.sources,
            "current_step": self.current_step,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    step_id = Column(Integer, nullable=False)
    action = Column(String(512), nullable=False)
    command = Column(Text, nullable=True)
    expected_outcome = Column(Text, nullable=True)
    rollback = Column(Text, nullable=True)
    is_destructive = Column(Integer, default=0)         # 0=false, 1=true
    requires_confirmation = Column(Integer, default=0)  # 0=false, 1=true
    status = Column(Enum(StepStatusEnum), default=StepStatusEnum.PENDING)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("Incident", back_populates="workflow_steps")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "step_id": self.step_id,
            "action": self.action,
            "command": self.command,
            "expected_outcome": self.expected_outcome,
            "rollback": self.rollback,
            "is_destructive": bool(self.is_destructive),
            "requires_confirmation": bool(self.requires_confirmation),
            "status": self.status.value if self.status else None,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class Escalation(Base):
    __tablename__ = "escalations"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    reason = Column(String(512), nullable=False)   # low_confidence | p1_severity | execution_failure
    summary = Column(Text, nullable=True)
    attempted_steps = Column(JSON, nullable=True)
    failure_reason = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    slack_status = Column(Enum(EscalationStatusEnum), default=EscalationStatusEnum.PENDING)
    pagerduty_status = Column(Enum(EscalationStatusEnum), default=EscalationStatusEnum.PENDING)
    slack_response = Column(JSON, nullable=True)
    pagerduty_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="escalation")

    def to_dict(self):
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "reason": self.reason,
            "summary": self.summary,
            "attempted_steps": self.attempted_steps,
            "failure_reason": self.failure_reason,
            "recommended_action": self.recommended_action,
            "slack_status": self.slack_status.value if self.slack_status else None,
            "pagerduty_status": self.pagerduty_status.value if self.pagerduty_status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── DB session factory ─────────────────────────────────────────────────────────

def get_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables(engine):
    Base.metadata.create_all(bind=engine)
