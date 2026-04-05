"""
Workflow Executor Agent — LangGraph node responsible for:
  1. Converting remediation_steps[] into a structured executable workflow
  2. Validating each step for safety (destructive command detection)
  3. Streaming step-by-step execution status via WebSocket
"""
import json
import logging
import os
import re
from typing import AsyncGenerator, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# Commands that are considered destructive and always require human confirmation
DESTRUCTIVE_PATTERNS = [
    r"kubectl\s+delete",
    r"kubectl\s+drain",
    r"kubectl\s+cordon",
    r"\bdrop\s+table\b",
    r"\btruncate\s+table\b",
    r"\bdelete\s+from\b",
    r"\brm\s+-rf\b",
    r"\brm\s+-f\b",
    r"format\s+[a-z/]",
    r"mkfs\.",
    r"dd\s+if=",
    r"shutdown\b",
    r"reboot\b",
    r"poweroff\b",
    r"systemctl\s+stop\s+(?!pgbouncer)",  # allow pgbouncer stop, not others
    r"pg_drop_replication_slot",
    r"dropdb\b",
]

DESTRUCTIVE_RE = re.compile("|".join(DESTRUCTIVE_PATTERNS), re.IGNORECASE)


# ── State ──────────────────────────────────────────────────────────────────────

class WorkflowState(TypedDict):
    incident_id: int
    remediation_steps: list[str]
    severity: str
    # outputs
    workflow: list[dict]    # list of WorkflowStep dicts
    error: str | None


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm():
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", temperature=0.0)
    elif os.getenv("COHERE_API_KEY"):
        from langchain_cohere import ChatCohere
        return ChatCohere(model="command-r-plus", temperature=0.0)
    else:
        raise EnvironmentError("Set OPENAI_API_KEY or COHERE_API_KEY.")


# ── Prompts ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are AURA Workflow Planner. Convert a list of remediation steps into a structured 
executable workflow. Each step must have a concrete, runnable command or action.

Return a JSON array where each element has:
{
  "step_id": <integer starting at 1>,
  "action": "<brief human-readable action title>",
  "command": "<exact shell command or API call to execute, or null if not applicable>",
  "expected_outcome": "<what success looks like>",
  "rollback": "<exact command to undo this step, or null>"
}

Rules:
- If a step involves destructive operations (deleting, dropping, force removing), 
  prefix the command with "# [REQUIRES CONFIRMATION] "
- Keep commands specific and runnable
- For steps requiring human judgment, set command to null and describe in action
- Provide rollback commands wherever possible
"""

def _build_workflow_prompt(steps: list[str], severity: str) -> str:
    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
    return f"""\
Incident Severity: {severity}

Remediation Steps to Convert:
{steps_text}

Convert these into a structured executable workflow JSON array.
"""


# ── Safety validation ──────────────────────────────────────────────────────────

def _is_destructive(command: str | None) -> bool:
    if not command:
        return False
    return bool(DESTRUCTIVE_RE.search(command)) or "[REQUIRES CONFIRMATION]" in command


def _validate_step(step: dict) -> dict:
    """Enrich a workflow step with safety flags."""
    command = step.get("command") or ""
    destructive = _is_destructive(command)
    return {
        **step,
        "is_destructive": destructive,
        "requires_confirmation": destructive,
        "status": "pending",
        "output": None,
        "error": None,
    }


# ── LangGraph node function ────────────────────────────────────────────────────

def workflow_node(state: WorkflowState) -> WorkflowState:
    """
    LangGraph node: remediation_steps → structured workflow with safety validation.
    """
    remediation_steps = state.get("remediation_steps", [])
    severity = state.get("severity", "P3")

    logger.info(
        "Workflow agent generating plan for incident %d (%d steps)",
        state["incident_id"], len(remediation_steps),
    )

    if not remediation_steps:
        return {
            **state,
            "workflow": [],
            "error": "No remediation steps provided.",
        }

    try:
        llm = _get_llm()
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_workflow_prompt(remediation_steps, severity)),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])

        workflow_raw: list[dict] = json.loads(raw)
        workflow = [_validate_step(step) for step in workflow_raw]

        logger.info(
            "Workflow generated for incident %d: %d steps (%d require confirmation)",
            state["incident_id"],
            len(workflow),
            sum(1 for s in workflow if s.get("requires_confirmation")),
        )

        return {**state, "workflow": workflow, "error": None}

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse workflow LLM response: %s", exc)
        # Fallback: convert each step to a minimal workflow entry
        fallback = [
            _validate_step({
                "step_id": i + 1,
                "action": step,
                "command": None,
                "expected_outcome": "Verify manually",
                "rollback": None,
            })
            for i, step in enumerate(remediation_steps)
        ]
        return {**state, "workflow": fallback, "error": f"JSON parse error; using fallback: {exc}"}

    except Exception as exc:
        logger.exception("Workflow agent failed for incident %d: %s", state["incident_id"], exc)
        return {**state, "workflow": [], "error": str(exc)}


# ── Step simulator (used during WebSocket streaming) ──────────────────────────

async def simulate_step_execution(
    step: dict,
) -> AsyncGenerator[dict, None]:
    """
    Simulate executing a single workflow step.
    In production, replace this with actual command execution via subprocess or k8s API.
    Yields status update dicts.
    """
    import asyncio

    step_id = step.get("step_id", 0)
    command = step.get("command")
    action = step.get("action", "")

    yield {"step_id": step_id, "status": "running", "message": f"Starting: {action}"}
    await asyncio.sleep(0.5)

    if step.get("requires_confirmation") and not step.get("confirmed", False):
        yield {
            "step_id": step_id,
            "status": "awaiting_confirmation",
            "message": f"[REQUIRES HUMAN CONFIRMATION] Destructive command detected: {command}",
        }
        return

    # Simulate execution delay
    await asyncio.sleep(1.5)

    # Mock success
    yield {
        "step_id": step_id,
        "status": "done",
        "message": f"Completed: {action}",
        "output": f"Simulated output for: {command or action}",
    }
