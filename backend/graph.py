"""
AURA LangGraph Pipeline — wires all agents into directed graphs.

Two separate graphs:
  1. ingestion_graph   — for runbook upload + indexing
  2. diagnosis_graph   — for incident diagnosis + workflow generation + escalation
"""
import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agents.diagnosis_agent import DiagnosisState, diagnosis_node
from agents.escalation_agent import EscalationState, escalation_node
from agents.ingestion_agent import IngestionState, ingestion_node
from agents.workflow_agent import WorkflowState, workflow_node

logger = logging.getLogger(__name__)


# ── Ingestion Graph ────────────────────────────────────────────────────────────

def build_ingestion_graph():
    """
    Simple linear graph:
      START → ingestion_node → END
    """
    graph = StateGraph(IngestionState)
    graph.add_node("ingestion", ingestion_node)
    graph.add_edge(START, "ingestion")
    graph.add_edge("ingestion", END)
    return graph.compile()


# ── Diagnosis Graph ────────────────────────────────────────────────────────────

class IncidentPipelineState(DiagnosisState, WorkflowState, EscalationState):
    """
    Merged state for the full incident pipeline.
    All fields are optional at any given node; each agent fills its slice.
    """
    pass


def _should_escalate(state: IncidentPipelineState) -> Literal["escalate", "workflow"]:
    """Conditional edge: route to escalation or directly to workflow."""
    # Always generate the workflow; escalation runs in parallel conceptually,
    # but in a linear graph we run workflow first, then escalate if needed.
    return "workflow"


def _after_workflow(state: IncidentPipelineState) -> Literal["escalate", END]:
    """After workflow generation, escalate if needed."""
    if state.get("needs_escalation", False):
        return "escalate"
    return END


async def build_diagnosis_graph():
    """
    Incident pipeline graph:
      START → diagnosis_node → workflow_node → [escalation_node?] → END
    """
    graph = StateGraph(IncidentPipelineState)

    graph.add_node("diagnosis", diagnosis_node)
    graph.add_node("workflow", workflow_node)
    graph.add_node("escalation", escalation_node)

    graph.add_edge(START, "diagnosis")
    graph.add_edge("diagnosis", "workflow")
    graph.add_conditional_edges(
        "workflow",
        _after_workflow,
        {"escalate": "escalation", END: END},
    )
    graph.add_edge("escalation", END)

    return graph.compile()


# ── Convenience runners ────────────────────────────────────────────────────────

def run_ingestion(
    file_path: str,
    original_filename: str,
    file_type: str,
    runbook_id: int,
) -> IngestionState:
    """Run the ingestion pipeline synchronously."""
    graph = build_ingestion_graph()
    initial_state: IngestionState = {
        "file_path": file_path,
        "original_filename": original_filename,
        "file_type": file_type,
        "runbook_id": runbook_id,
        "chunks": [],
        "chunk_count": 0,
        "error": None,
        "status": "processing",
    }
    result = graph.invoke(initial_state)
    return result


async def run_diagnosis_pipeline(
    incident_id: int,
    description: str,
    severity: str,
    system_affected: str,
    attempted_steps: list[dict] | None = None,
) -> IncidentPipelineState:
    """Run the full diagnosis → workflow → escalation pipeline."""
    graph = await build_diagnosis_graph()
    initial_state: IncidentPipelineState = {
        # DiagnosisState fields
        "incident_id": incident_id,
        "incident_description": description,
        "severity": severity,
        "system_affected": system_affected,
        "root_cause": "",
        "confidence_score": 0.0,
        "remediation_steps": [],
        "sources": [],
        "needs_escalation": False,
        # WorkflowState fields
        "workflow": [],
        # EscalationState fields
        "attempted_steps": attempted_steps or [],
        "escalation_report": {},
        "slack_status": "skipped",
        "pagerduty_status": "skipped",
        "slack_response": None,
        "pagerduty_response": None,
        "escalation_reason": "",
        "error": None,
    }
    result = await graph.ainvoke(initial_state)
    return result
