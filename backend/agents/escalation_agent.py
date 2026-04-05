"""
Escalation Agent — LangGraph node responsible for:
  1. Monitoring confidence_score and severity from Diagnosis Agent
  2. Generating a structured escalation report
  3. POSTing to mock Slack and PagerDuty webhook endpoints
  4. Enforcing safe guardrails (no auto-execution of destructive commands)
"""
import json
import logging
import os
from typing import TypedDict

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.6


# ── State ──────────────────────────────────────────────────────────────────────

class EscalationState(TypedDict):
    incident_id: int
    incident_description: str
    severity: str
    system_affected: str
    root_cause: str
    confidence_score: float
    remediation_steps: list[str]
    attempted_steps: list[dict]
    needs_escalation: bool
    # outputs
    escalation_report: dict
    slack_status: str       # "sent" | "failed" | "skipped"
    pagerduty_status: str
    slack_response: dict | None
    pagerduty_response: dict | None
    escalation_reason: str
    error: str | None


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm():
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", temperature=0.2)
    elif os.getenv("COHERE_API_KEY"):
        from langchain_cohere import ChatCohere
        return ChatCohere(model="command-r-plus", temperature=0.2)
    else:
        raise EnvironmentError("Set OPENAI_API_KEY or COHERE_API_KEY.")


# ── Report generation ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are AURA Escalation Manager. Generate a structured on-call escalation report.

Return a JSON object with:
{
  "incident_summary": "<1-2 sentence summary of the incident>",
  "attempted_steps": ["<step 1>", "<step 2>", ...],
  "failure_reason": "<why automated resolution failed or was insufficient>",
  "recommended_on_call_action": "<specific action the on-call engineer should take first>",
  "risk_assessment": "<brief risk if not addressed immediately>",
  "estimated_impact": "<user/system impact description>"
}
"""

def _build_escalation_prompt(state: EscalationState) -> str:
    attempted = state.get("attempted_steps", [])
    steps_text = "\n".join(
        f"- Step {s.get('step_id', i+1)}: {s.get('action', 'Unknown')} [{s.get('status', 'unknown')}]"
        for i, s in enumerate(attempted)
    ) or "No steps attempted yet."

    return f"""\
INCIDENT DETAILS:
- ID: {state['incident_id']}
- Description: {state['incident_description']}
- Severity: {state['severity']}
- System Affected: {state['system_affected']}
- Root Cause (AI): {state.get('root_cause', 'Not determined')}
- AI Confidence Score: {state.get('confidence_score', 0.0):.2f}

ESCALATION REASON: {state.get('escalation_reason', 'Unknown')}

ATTEMPTED REMEDIATION STEPS:
{steps_text}

Generate a structured escalation report as JSON.
"""


# ── Webhook delivery ───────────────────────────────────────────────────────────

def _build_slack_payload(report: dict, incident_id: int, severity: str) -> dict:
    color = {"P1": "#FF0000", "P2": "#FFA500", "P3": "#FFFF00"}.get(severity, "#808080")
    return {
        "text": f":rotating_light: *AURA Incident Escalation — {severity}*",
        "attachments": [
            {
                "color": color,
                "fields": [
                    {"title": "Incident ID", "value": str(incident_id), "short": True},
                    {"title": "Severity", "value": severity, "short": True},
                    {"title": "Summary", "value": report.get("incident_summary", "N/A"), "short": False},
                    {"title": "Failure Reason", "value": report.get("failure_reason", "N/A"), "short": False},
                    {"title": "Recommended Action", "value": report.get("recommended_on_call_action", "N/A"), "short": False},
                    {"title": "Risk", "value": report.get("risk_assessment", "N/A"), "short": False},
                ],
                "footer": "AURA Incident Response System",
            }
        ],
    }


def _build_pagerduty_payload(report: dict, incident_id: int, severity: str) -> dict:
    urgency_map = {"P1": "high", "P2": "high", "P3": "low"}
    return {
        "routing_key": os.getenv("PAGERDUTY_ROUTING_KEY", "mock-key"),
        "event_action": "trigger",
        "payload": {
            "summary": f"[AURA] {severity}: {report.get('incident_summary', 'Incident requires attention')}",
            "severity": "critical" if severity == "P1" else "error" if severity == "P2" else "warning",
            "source": f"aura-incident-{incident_id}",
            "custom_details": {
                "incident_id": incident_id,
                "root_cause": report.get("failure_reason", ""),
                "recommended_action": report.get("recommended_on_call_action", ""),
                "estimated_impact": report.get("estimated_impact", ""),
            },
        },
        "client": "AURA Incident Response",
        "client_url": f"http://localhost:3000/incidents/{incident_id}",
    }


async def _send_slack(payload: dict) -> tuple[str, dict]:
    """Send to Slack webhook. Returns (status, response_dict)."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook_url or "MOCK" in webhook_url.upper():
        logger.info("Slack webhook is mock — simulating delivery")
        return "sent", {"ok": True, "mock": True, "message": "Mock delivery simulated"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            return "sent", {"status_code": resp.status_code, "body": resp.text}
    except Exception as exc:
        logger.error("Slack webhook delivery failed: %s", exc)
        return "failed", {"error": str(exc)}


async def _send_pagerduty(payload: dict) -> tuple[str, dict]:
    """Send to PagerDuty Events API v2. Returns (status, response_dict)."""
    routing_key = os.getenv("PAGERDUTY_ROUTING_KEY", "")
    if not routing_key or routing_key == "mock-routing-key":
        logger.info("PagerDuty key is mock — simulating delivery")
        return "sent", {"status": "success", "mock": True, "message": "Mock PagerDuty event triggered"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return "sent", resp.json()
    except Exception as exc:
        logger.error("PagerDuty delivery failed: %s", exc)
        return "failed", {"error": str(exc)}


# ── LangGraph node function ────────────────────────────────────────────────────

async def escalation_node(state: EscalationState) -> EscalationState:
    """
    LangGraph node: generate escalation report → deliver to Slack + PagerDuty.
    Only runs if needs_escalation is True.
    """
    if not state.get("needs_escalation", False):
        return {
            **state,
            "escalation_report": {},
            "slack_status": "skipped",
            "pagerduty_status": "skipped",
            "slack_response": None,
            "pagerduty_response": None,
            "escalation_reason": "not_needed",
            "error": None,
        }

    # Determine escalation reason
    reason_parts = []
    if state.get("confidence_score", 1.0) < CONFIDENCE_THRESHOLD:
        reason_parts.append(f"low_confidence ({state['confidence_score']:.2f} < {CONFIDENCE_THRESHOLD})")
    if state.get("severity") == "P1":
        reason_parts.append("p1_severity")
    if not reason_parts:
        reason_parts.append("manual_trigger")
    escalation_reason = " + ".join(reason_parts)

    logger.info(
        "Escalation agent triggered for incident %d: %s",
        state["incident_id"], escalation_reason,
    )

    try:
        # 1. Generate structured escalation report
        llm = _get_llm()
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_escalation_prompt({**state, "escalation_reason": escalation_reason})),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])

        report = json.loads(raw)

    except Exception as exc:
        logger.error("Failed to generate escalation report: %s", exc)
        report = {
            "incident_summary": state.get("incident_description", "")[:200],
            "failure_reason": f"Automated escalation report generation failed: {exc}",
            "recommended_on_call_action": "Review incident manually.",
            "risk_assessment": "Unknown — review required.",
            "estimated_impact": "Unknown",
        }

    # 2. Deliver webhooks
    incident_id = state["incident_id"]
    severity = state["severity"]

    slack_payload = _build_slack_payload(report, incident_id, severity)
    pd_payload = _build_pagerduty_payload(report, incident_id, severity)

    slack_status, slack_resp = await _send_slack(slack_payload)
    pd_status, pd_resp = await _send_pagerduty(pd_payload)

    logger.info(
        "Escalation delivered for incident %d: slack=%s pagerduty=%s",
        incident_id, slack_status, pd_status,
    )

    return {
        **state,
        "escalation_report": report,
        "slack_status": slack_status,
        "pagerduty_status": pd_status,
        "slack_response": slack_resp,
        "pagerduty_response": pd_resp,
        "escalation_reason": escalation_reason,
        "error": None,
    }
