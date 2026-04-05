"""
Diagnosis Agent — LangGraph node responsible for:
  1. Embedding the incident description
  2. Retrieving top-5 relevant runbook chunks via RAG
  3. Prompting the LLM to identify root cause + remediation steps
  4. Returning structured diagnosis with confidence score
"""
import json
import logging
import os
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from vector_store import similarity_search_with_score

logger = logging.getLogger(__name__)

RETRIEVAL_K = 5
CONFIDENCE_THRESHOLD = 0.6


# ── State ──────────────────────────────────────────────────────────────────────

class DiagnosisState(TypedDict):
    incident_id: int
    incident_description: str
    severity: str           # P1 | P2 | P3
    system_affected: str
    # outputs
    root_cause: str
    confidence_score: float
    remediation_steps: list[str]
    sources: list[dict]
    needs_escalation: bool
    error: str | None


# ── LLM factory ───────────────────────────────────────────────────────────────

def _get_llm():
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", temperature=0.1)
    elif os.getenv("COHERE_API_KEY"):
        from langchain_cohere import ChatCohere
        return ChatCohere(model="command-r-plus", temperature=0.1)
    else:
        raise EnvironmentError("Set OPENAI_API_KEY or COHERE_API_KEY.")


# ── Prompt construction ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are AURA, an expert Site Reliability Engineer AI assistant.
Your job is to diagnose incidents and provide actionable remediation steps.

You will be given:
1. An incident description with severity and affected system
2. Relevant runbook sections retrieved from the knowledge base

Your response MUST be valid JSON with this exact structure:
{
  "root_cause": "<concise explanation of the likely root cause>",
  "confidence_score": <float 0.0-1.0 indicating your confidence>,
  "remediation_steps": [
    "<step 1>",
    "<step 2>",
    ...
  ],
  "reasoning": "<brief explanation of how you arrived at this diagnosis>"
}

Guidelines:
- confidence_score should reflect how well the runbook content matches the incident
- If runbook content is highly relevant: 0.75-1.0
- If runbook content is partially relevant: 0.4-0.74
- If no clear match found: 0.0-0.39
- remediation_steps should be specific, ordered, and actionable
- Do NOT include destructive commands without a warning prefix: "[REQUIRES CONFIRMATION]"
"""

def _build_user_prompt(
    description: str,
    severity: str,
    system_affected: str,
    retrieved_chunks: list[tuple],
) -> str:
    runbook_context = "\n\n".join(
        f"--- Source: {doc.metadata.get('source_file', 'unknown')} | "
        f"Section: {doc.metadata.get('section_title', 'N/A')} | "
        f"Page: {doc.metadata.get('page_number', 'N/A')} ---\n{doc.page_content}"
        for doc, _score in retrieved_chunks
    )

    return f"""\
INCIDENT REPORT:
- Description: {description}
- Severity: {severity}
- System Affected: {system_affected}

RELEVANT RUNBOOK SECTIONS:
{runbook_context}

Based on the incident and the runbook sections above, provide your diagnosis as JSON.
"""


# ── LangGraph node function ────────────────────────────────────────────────────

def diagnosis_node(state: DiagnosisState) -> DiagnosisState:
    """
    LangGraph node: RAG retrieval → LLM diagnosis → structured output.
    """
    description = state["incident_description"]
    severity = state["severity"]
    system_affected = state["system_affected"]

    logger.info(
        "Diagnosis agent started for incident %d [%s] affecting %s",
        state["incident_id"], severity, system_affected,
    )

    try:
        # 1. Retrieve relevant runbook chunks
        query = f"{description} system:{system_affected}"
        retrieved = similarity_search_with_score(query, k=RETRIEVAL_K)

        if not retrieved:
            logger.warning("No runbook chunks retrieved for incident %d", state["incident_id"])

        # 2. Build sources list
        sources = [
            {
                "source_file": doc.metadata.get("source_file", "unknown"),
                "section_title": doc.metadata.get("section_title", "N/A"),
                "page_number": doc.metadata.get("page_number", 0),
                "relevance_score": round(float(score), 4),
                "excerpt": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
            }
            for doc, score in retrieved
        ]

        # 3. Call LLM
        llm = _get_llm()
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_user_prompt(description, severity, system_affected, retrieved)),
        ]
        response = llm.invoke(messages)
        raw_content = response.content.strip()

        # 4. Parse JSON response
        # Strip markdown code fences if present
        if raw_content.startswith("```"):
            raw_content = "\n".join(raw_content.split("\n")[1:])
        if raw_content.endswith("```"):
            raw_content = "\n".join(raw_content.split("\n")[:-1])

        result = json.loads(raw_content)
        root_cause = result.get("root_cause", "Unable to determine root cause.")
        confidence_score = float(result.get("confidence_score", 0.5))
        remediation_steps = result.get("remediation_steps", [])

        # 5. Determine escalation need
        needs_escalation = confidence_score < CONFIDENCE_THRESHOLD or severity == "P1"

        logger.info(
            "Diagnosis complete for incident %d: confidence=%.2f, escalate=%s",
            state["incident_id"], confidence_score, needs_escalation,
        )

        return {
            **state,
            "root_cause": root_cause,
            "confidence_score": confidence_score,
            "remediation_steps": remediation_steps,
            "sources": sources,
            "needs_escalation": needs_escalation,
            "error": None,
        }

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM JSON response: %s", exc)
        return {
            **state,
            "root_cause": "Diagnosis failed: could not parse LLM response.",
            "confidence_score": 0.0,
            "remediation_steps": [],
            "sources": [],
            "needs_escalation": True,
            "error": f"JSON parse error: {exc}",
        }
    except Exception as exc:
        logger.exception("Diagnosis agent failed for incident %d: %s", state["incident_id"], exc)
        return {
            **state,
            "root_cause": "Diagnosis failed due to an internal error.",
            "confidence_score": 0.0,
            "remediation_steps": [],
            "sources": [],
            "needs_escalation": True,
            "error": str(exc),
        }
