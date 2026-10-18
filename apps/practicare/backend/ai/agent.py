"""
PractiCare LangGraph Autonomous AI Agent
Orchestrates clinical intelligence workflows using Google Gemini API and LangGraph StateGraph:
  START -> AGENT_REASONING -> TOOL_EXECUTION -> RESULT_ANALYSIS -> REPORT_SYNTHESIS -> END

Enforces:
  - Real Google Gemini API reasoning with dynamic tool binding from ToolRegistry
  - Zero-trust tool dispatch strictly through ToolGateway.execute()
  - Dynamic role-based schema exposure based on verified SecurityContext
  - Multi-step execution & loop protection (max iterations, duplicate call prevention)
  - Human-in-the-Loop approval workflows for HIGH risk actions
  - Deterministic clinical reasoning fallback when explicitly configured (AI_AGENT_MODE=deterministic)
  - Accurate, structured error reporting for provider failures (quota, auth, network)
"""

import os
import re
import time
import json
import logging
import uuid
from typing import Dict, Any, List, Optional, TypedDict
from datetime import date, timedelta
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Load local environment variables securely
load_dotenv()

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
    from langchain_core.runnables import RunnableConfig
    LANGGRAPH_AVAILABLE = True
except ImportError:
    StateGraph = START = END = MemorySaver = None
    SystemMessage = HumanMessage = AIMessage = ToolMessage = RunnableConfig = None
    LANGGRAPH_AVAILABLE = False

from ai.context import SecurityContext
from ai.registry import registry, INVENTORY_WRITE_TOOLS
from ai.gateway import gateway, ToolGateway
from ai.approvals import approval_manager

logger = logging.getLogger("practicare.ai.agent")


MAX_ITERATIONS = 3
MAX_TOTAL_TOOLS = 5
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

# Gemini token pricing (Flash-Lite Tier: $0.075 / 1M input, $0.30 / 1M output)
INPUT_TOKEN_PRICE_PER_MILLION = 0.075
OUTPUT_TOKEN_PRICE_PER_MILLION = 0.30


class AgentState(TypedDict):
    message: str
    conversation_id: Optional[str]
    conversation_history: List[Dict[str, Any]]
    tenant_id: str
    user_id: str
    user_role: str
    company_name: str
    approval_id: Optional[str]
    current_iteration: int
    tool_calls_planned: List[Dict[str, Any]]
    executed_tools: List[Dict[str, Any]]
    tool_results: Dict[str, Any]
    approval_pending: Optional[Dict[str, Any]]
    more_tools_needed: bool
    final_reply: Optional[str]
    status: str
    metrics: Dict[str, Any]
    agent_mode: str
    model_name: str
    model_calls: int
    input_tokens: int
    output_tokens: int
    llm_latency_ms: float
    langchain_messages: List[Any]


def _resolve_context_and_db(state: AgentState, config: Optional[RunnableConfig] = None):
    configurable = config.get("configurable", {}) if config else {}
    db = configurable.get("db")
    context = configurable.get("context")
    if not context:
        raise ValueError("Verified SecurityContext missing from LangGraph execution config")
    return context, db


def _extract_text_content(content: Any) -> str:
    """Extracts string representation from either str or list of content dicts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _extract_usage(response: Any) -> tuple:
    usage = getattr(response, "usage_metadata", {}) or {}
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    return inp, out


def get_gemini_llm(temperature: float = 0.0):
    """
    Initializes ChatGoogleGenerativeAI with the exact configured GEMINI_MODEL.
    Uses 60s timeout. Does not silently remap models.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY in backend environment.")

    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()

    llm = ChatGoogleGenerativeAI(
        model=configured_model,
        temperature=temperature,
        google_api_key=api_key,
        max_retries=0,  # Managed by invoke_gemini_with_retry for fine-grained transient error handling
        timeout=60.0,
    )
    return llm, configured_model


def invoke_gemini_with_retry(runnable, messages, max_transient_retries: int = 2):
    """
    Invokes Gemini with bounded exponential-backoff retries for transient errors
    (503 UNAVAILABLE, 504 DEADLINE_EXCEEDED, network timeout/reset).
    Never retries 429 RESOURCE_EXHAUSTED or 400 INVALID_ARGUMENT.
    Respects Retry-After guidance when provided.
    """
    attempt = 0
    backoff = 2.0
    while True:
        try:
            return runnable.invoke(messages)
        except Exception as exc:
            err_str = str(exc)
            # Never retry terminal quota exhaustion or invalid auth
            if any(t in err_str for t in ("429", "RESOURCE_EXHAUSTED", "400", "401", "403", "404", "INVALID_ARGUMENT", "API_KEY_INVALID")):
                raise exc

            # Transient errors eligible for retry
            is_transient = any(t in err_str for t in ("503", "UNAVAILABLE", "504", "DEADLINE_EXCEEDED", "timeout", "Timeout", "ConnectionReset", "forcibly closed", "temporarily unavailable"))
            if is_transient and attempt < max_transient_retries:
                attempt += 1
                wait_sec = backoff
                retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                if retry_match:
                    try:
                        wait_sec = min(float(retry_match.group(1)), 10.0)
                    except Exception:
                        pass
                logger.warning("Transient Gemini error (%s). Retrying %d/%d after %.1fs...", err_str[:80], attempt, max_transient_retries, wait_sec)
                time.sleep(wait_sec)
                backoff *= 2.0
            else:
                raise exc


# ==============================================================================
# CLINICAL ENTITY & VERIFICATION HELPERS
# ==============================================================================

def _claims_task_creation(text: Optional[str]) -> bool:
    """Detects if a reply claims that a task has been created or scheduled."""
    if not text:
        return False
    lower = text.lower()
    patterns = [
        r'task\s+(?:has\s+been\s+|is\s+)?(?:successfully\s+)?(?:created|scheduled)',
        r'scheduled\s+(?:the\s+)?clinical\s+task',
        r'created\s+(?:the\s+)?clinical\s+task',
        r'task\s+successfully\s+created',
        r'\btask\s+id[:\s]+\**tsk-',
        r'\*+\s*task\s+id\s*\*+[:\s]+tsk-',
    ]
    return any(bool(re.search(p, lower)) for p in patterns)


def _has_verified_task_creation(tool_results: Dict[str, Any], executed: List[Dict[str, Any]]) -> bool:
    """Verifies that create_clinical_task was actually executed and persisted in PostgreSQL."""
    ct_res = tool_results.get("create_clinical_task")
    if isinstance(ct_res, dict) and ct_res.get("status") == "SUCCESS" and ct_res.get("task_id") and ct_res.get("persisted"):
        return True
    for t in executed:
        t_name = t.get("tool_name") or t.get("tool")
        t_status = t.get("execution_status") or t.get("status")
        if t_name == "create_clinical_task" and t_status == "SUCCESS":
            res = t.get("result", {})
            if isinstance(res, dict) and (res.get("persisted") or res.get("task_id") or t.get("persisted")):
                return True
    return False


def _has_verified_checklist_update(tool_results: Dict[str, Any], executed: List[Dict[str, Any]]) -> bool:
    """Verifies that update_checklist or update_checklist_status was actually executed and persisted."""
    for t in executed:
        t_name = t.get("tool_name") or t.get("tool")
        t_status = t.get("execution_status") or t.get("status")
        if t_name in ("update_checklist", "update_checklist_status") and t_status == "SUCCESS":
            res = t.get("result", {})
            if isinstance(res, dict) and (res.get("persisted") is True or t.get("persisted") is True):
                return True
    return False


def _has_verified_room_update(tool_results: Dict[str, Any], executed: List[Dict[str, Any]]) -> bool:
    """Verifies that update_room was actually executed and persisted in PostgreSQL."""
    for t in executed:
        t_name = t.get("tool_name") or t.get("tool")
        t_status = t.get("execution_status") or t.get("status")
        if t_name == "update_room" and t_status == "SUCCESS":
            res = t.get("result", {})
            if isinstance(res, dict) and (res.get("persisted") is True or t.get("persisted") is True):
                return True
    return False


def _has_verified_room_creation(tool_results: Dict[str, Any], executed: List[Dict[str, Any]]) -> bool:
    """Verifies that create_room was executed and persisted."""
    for t in executed:
        t_name = t.get("tool_name") or t.get("tool")
        t_status = t.get("execution_status") or t.get("status")
        if t_name == "create_room" and t_status == "SUCCESS":
            return True
    return False


def _has_verified_checklist_creation(tool_results: Dict[str, Any], executed: List[Dict[str, Any]]) -> bool:
    """Verifies that create_checklist was executed and persisted."""
    for t in executed:
        t_name = t.get("tool_name") or t.get("tool")
        t_status = t.get("execution_status") or t.get("status")
        if t_name == "create_checklist" and t_status == "SUCCESS":
            return True
    return False


def _claims_checklist_update(text: Optional[str]) -> bool:
    """Detects if a reply claims that a checklist has been updated or assigned."""
    if not text:
        return False
    lower = text.lower()
    patterns = [
        r'checklist\s+(?:has\s+been\s+|is\s+)?(?:successfully\s+)?(?:assigned|updated|reassigned)',
        r'assigned\s+(?:the\s+)?checklist',
        r'reassigned\s+(?:the\s+)?checklist',
        r'checklist\s+successfully\s+assigned',
        r'checklist\s+successfully\s+updated',
    ]
    return any(bool(re.search(p, lower)) for p in patterns)


def _claims_room_update(text: Optional[str]) -> bool:
    """Detects if a reply claims that a room status or room has been updated."""
    if not text:
        return False
    lower = text.lower()
    patterns = [
        r'room\s+(?:status\s+)?(?:has\s+been\s+|is\s+)?(?:successfully\s+)?(?:updated|changed|set)',
        r'changed\s+(?:the\s+)?room\s+status',
        r'updated\s+(?:the\s+)?room\s+status',
        r'status\s+of\s+room\s+[0-9a-zA-Z_-]+\s+(?:has\s+been\s+|is\s+)?(?:changed|updated|set)\s+to',
        r'room\s+[0-9a-zA-Z_-]+\s+is\s+now\s+(?:occupied|available|turnover)',
        r'room\s+status\s+successfully\s+updated',
    ]
    return any(bool(re.search(p, lower)) for p in patterns)


def _extract_recent_entity_from_history(history: Optional[List[Dict[str, Any]]], entity_type: str) -> Optional[str]:
    """Extracts the most recent resource ID from authorized conversation history."""
    if not history:
        return None
    for turn in reversed(history):
        content = str(turn.get("content") or "")
        if entity_type == "checklist":
            m = re.findall(r'\b((?:chk|check|checklist)-[a-zA-Z0-9_-]+)\b', content, re.IGNORECASE)
            if m:
                return m[-1].lower()
            m2 = re.findall(r'\bchecklist\s+(?:#|no\.?|number\s+)?([a-zA-Z0-9_-]+)\b', content, re.IGNORECASE)
            if m2:
                return m2[-1].lower()
        elif entity_type == "room":
            m = re.findall(r'\b(room-[a-zA-Z0-9_-]+)\b', content, re.IGNORECASE)
            if m:
                return m[-1]
            m_num = re.findall(r'\b(?:room|suite|bay)\s*#?\s*([0-9a-zA-Z_-]+)\b', content, re.IGNORECASE)
            if m_num:
                return m_num[-1]
        elif entity_type == "task":
            m = re.findall(r'\b(tsk-[a-zA-Z0-9_-]+)\b', content, re.IGNORECASE)
            if m:
                return m[-1].lower()
        elif entity_type == "staff":
            m = re.findall(r'\b(stf-[a-zA-Z0-9_-]+)\b', content, re.IGNORECASE)
            if m:
                return m[-1].lower()
    return None


PRONOUNS_AND_ANAPHORS = {
    "it", "them", "they", "their", "that", "this", "those",
    "that room", "the room", "that task", "the task", "that checklist", "the checklist",
    "the room you just created", "the room you created", "that room you created",
    "the checklist you just created", "the checklist you created", "that checklist you created",
    "the task you just created", "the task you created", "that task you created",
}


def _is_pronoun_or_anaphor(query: str) -> bool:
    clean = query.strip().lower()
    return clean in PRONOUNS_AND_ANAPHORS or clean in ("it", "them", "they", "their", "that", "this", "those")


def _detect_mutation_intent(message: str) -> Optional[str]:
    """Classifies an explicit write request; returns None for read-only or unclear requests."""
    lower = (message or "").lower()
    if _is_read_only_request(message):
        return None
    target = _creation_target(message)
    if target == "checklist":
        return "checklist_create"
    if target == "room":
        return "room_create"
    if _is_task_creation_request(message):
        return "task_create"
    if "checklist" in lower:
        # Tick/toggle first so "tick checklist check-assigned-xxx" is an update, not an assignment
        if re.search(r'\b(?:tick|untick|toggle|mark|complete|uncheck)\b', lower):
            return "checklist_update"
        if re.search(r'\b(?:assign|reassign|assigned\s+to)\b', lower):
            return "checklist_assign"
        if re.search(r'\bupdate\b', lower):
            return "checklist_update"
        return None
    if _is_inventory_mutation_request(message):
        return "inventory_change"
    if (
        re.search(r'\b(?:room|suite)\b', lower)
        and _ROOM_UPDATE_VERB.search(lower)
        and re.search(r'\b(?:occupied|available|turnover|status)\b', lower)
    ):
        return "room_update"
    if any(k in lower for k in ["complete task", "mark task", "update task", "reassign task", "mark completed"]):
        return "task_update"
    return None


_SUCCESS_CLAIM = re.compile(
    r"\b(?:successfully|has\s+been|have\s+been|is\s+now|are\s+now|persisted|created|updated|assigned|reassigned|completed|changed)\b"
)
_NEGATION = re.compile(r"\b(?:not|unable|cannot|failed|denied|forbidden)\b|n't\b")
# Database record identifiers generated by models.generate_id
_RESOURCE_ID = re.compile(r"\b(?:room|tsk|chk|stf|usr|inv|lev|appr|prac)-[a-z0-9]{4,}\b", re.IGNORECASE)


def _claims_room_creation(text: Optional[str]) -> bool:
    lower = (text or "").lower()
    return bool(re.search(r"\brooms?\s+(?:has|have)\s+been\s+(?:successfully\s+)?created|\bcreated\s+(?:the\s+)?(?:following\s+)?(?:\w+\s+)?rooms?\b", lower))


def _claims_checklist_creation(text: Optional[str]) -> bool:
    lower = (text or "").lower()
    return bool(re.search(r"\bchecklists?\s+(?:has|have)\s+been\s+(?:successfully\s+)?created|\bcreated\s+(?:the\s+)?(?:\w+\s+)?checklists?\b", lower))


def _tool_evidence(executed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every tool call made in this turn, in order (repeated calls of the same tool are all kept)."""
    return [
        {
            "tool": t.get("tool") or t.get("tool_name"),
            "arguments": {k: v for k, v in (t.get("args") or {}).items() if v is not None},
            "status": t.get("execution_status") or t.get("status"),
            "result": t.get("result"),
        }
        for t in executed
    ]


def _verified_write_lines(executed: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for t in executed:
        if t.get("is_read_only", True) or (t.get("execution_status") or t.get("status")) != "SUCCESS":
            continue
        res = t.get("result") or {}
        rid = t.get("resource_id") or res.get("resource_id")
        label = res.get("title") or res.get("name") or ""
        assignee = res.get("assigned_staff_name") or res.get("assigned_staff_id")
        line = f"- `{t.get('tool')}` → `{rid}`" + (f" — {label}" if label else "") + (f" (assigned to {assignee})" if assignee else "")
        lines.append(line)
    return lines


def _ground_resource_ids(
    reply: str,
    message: str,
    executed: List[Dict[str, Any]],
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Removes record IDs that do not appear in this turn's tool evidence or in the user's own words."""
    user_turns = [h.get("content") for h in (history or []) if h.get("role") == "user"]
    evidence = (json.dumps(_tool_evidence(executed), default=str) + " " + (message or "") + " " + json.dumps(user_turns, default=str)).lower()
    unverified = sorted({m.group(0) for m in _RESOURCE_ID.finditer(reply) if m.group(0).lower() not in evidence})
    if not unverified:
        return reply
    for rid in unverified:
        reply = re.sub(re.escape(rid), "[unverified ID removed]", reply)
    reply += (
        f"\n\n> ⚠️ **Verification notice:** {len(unverified)} identifier(s) in this response did not match any record "
        f"returned by the database tools and were removed."
    )
    written = _verified_write_lines(executed)
    if written:
        reply += "\n\n**Verified records from this request:**\n" + "\n".join(written)
    return reply


def _enforce_mutation_grounding(
    reply: str,
    message: str,
    context: SecurityContext,
    tool_results: Dict[str, Any],
    executed: List[Dict[str, Any]],
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Prevents false success AND false failure: a reply may only claim a mutation that a verified tool
    write in this turn supports, and may only cite record IDs present in the tool evidence.
    Read-only requests are never turned into "not updated" notices.
    """
    reply = _enforce_inventory_facts(reply, executed)
    if _is_read_only_request(message):
        return _ground_resource_ids(reply, message, executed, history)

    intent = _detect_mutation_intent(message)
    lower_reply = reply.lower()
    claims_success = bool(_SUCCESS_CLAIM.search(lower_reply)) and not _NEGATION.search(lower_reply)

    checks = [
        # (reply claims this mutation, verified write exists, notice)
        (
            _claims_checklist_update(reply) or (intent in ("checklist_assign", "checklist_update") and claims_success),
            _has_verified_checklist_update(tool_results, executed) or _has_verified_checklist_creation(tool_results, executed),
            "The checklist change was not completed: no checklist update was executed or persisted",
        ),
        (
            _claims_room_update(reply) or (intent == "room_update" and claims_success),
            _has_verified_room_update(tool_results, executed),
            "The room status was not updated: no room update was executed or persisted",
        ),
        (
            _claims_task_creation(reply) or (intent == "task_create" and claims_success),
            _has_verified_task_creation(tool_results, executed),
            "The task was not created: no task creation was executed or persisted",
        ),
        (
            _claims_room_creation(reply) or (intent == "room_create" and claims_success),
            _has_verified_room_creation(tool_results, executed),
            "The room was not created: no room creation was executed or persisted",
        ),
        (
            _claims_checklist_creation(reply) or (intent == "checklist_create" and claims_success),
            _has_verified_checklist_creation(tool_results, executed),
            "The checklist was not created: no checklist creation was executed or persisted",
        ),
    ]
    attempted_inventory_write = any(t.get("tool") in INVENTORY_WRITE_TOOLS for t in executed)
    checks.append((
        (intent == "inventory_change" or attempted_inventory_write) and _claims_inventory_change(reply),
        _has_verified_inventory_write(executed),
        "The inventory change was not completed: no inventory write was executed or persisted",
    ))
    for claimed, verified, notice in checks:
        if claimed and not verified:
            return (
                f"### ⚠️ Action Not Completed\n\n"
                f"> **[PERSISTENCE_NOT_VERIFIED]** {notice} in PostgreSQL for tenant `{context.tenant_id}`."
            )

    reply = _ground_resource_ids(reply, message, executed, history)

    # A write was requested but nothing was written and the reply does not say so: state it plainly.
    if intent and not any(not t.get("is_read_only", True) and (t.get("execution_status") or t.get("status")) == "SUCCESS" for t in executed):
        if not claims_success:
            reply += "\n\n> ℹ️ No database change was made for this request."
    return reply


def _extract_staff_query(message: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
    m = re.search(r'\b(stf-[a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    if "," in message:
        parts = [p.strip() for p in message.split(",") if p.strip()]
        for p in reversed(parts):
            p_lower = p.lower()
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', p) and p_lower not in ("high", "medium", "low", "critical") and not re.match(r'^(?:room|suite|bay)?\s*#?\d+$', p_lower):
                if not _is_pronoun_or_anaphor(p):
                    return p
    m_for = re.search(r'(?:for|assign(?:ed)?\s+to)\s+(?:dr\.?|doctor|nurse\s+)?([A-Za-z]+(?:\s+[A-Za-z]+)?)', message, re.IGNORECASE)
    if m_for:
        candidate = m_for.group(1).strip()
        if not _is_pronoun_or_anaphor(candidate):
            return candidate
    m_name = re.search(r'(?:dr\.?|doctor|nurse)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)', message, re.IGNORECASE)
    if m_name:
        candidate = m_name.group(0).strip()
        if not _is_pronoun_or_anaphor(candidate):
            return candidate

    lower = message.lower()
    # Pronoun resolution from history (e.g. "show their pending tasks")
    if any(p in lower for p in ["their", "them", "they", "his", "her"]):
        recent_staff = _extract_recent_entity_from_history(history, "staff")
        if recent_staff:
            return recent_staff

    if any(k in lower for k in ["find staff", "search staff", "lookup staff", "who is on shift", "staff member", "staff directory"]):
        cleaned = re.sub(r'(?i)^(find|search|lookup|who is|show)\s+(the\s+|for\s+)?(staff|provider|member|doctor|nurse)?\s*', '', message).strip()
        if cleaned and not _is_pronoun_or_anaphor(cleaned):
            return cleaned
    return ""


def _extract_task_id(message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    m = re.search(r'\b(tsk-[a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m2 = re.search(r'\btask-([a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m2:
        return f"tsk-{m2.group(1)}".lower()
    m3 = re.search(r'\btask\s+(?:#|no\.?|number\s+)?([a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m3:
        val = m3.group(1).strip().lower()
        if val not in ("status", "creation", "details"):
            return f"tsk-{val}" if not val.startswith("tsk-") else val
    m4 = re.search(r'\b(\d+)\b', message)
    if m4:
        return f"tsk-{m4.group(1)}".lower()

    # Contextual reference resolution (e.g. "show the task you created")
    recent = _extract_recent_entity_from_history(history, "task")
    if recent:
        return recent
    return None


def _extract_staff_id(message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    m = re.search(r'\b(stf-[a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    if history and any(p in message.lower() for p in ["their", "them", "they", "him", "her"]):
        return _extract_recent_entity_from_history(history, "staff")
    return None


def _extract_checklist_id(message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    m = re.search(r'\b((?:chk|check|checklist)-[a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m2 = re.search(r'\bchecklist\s+(?:#|no\.?|number\s+)?([a-zA-Z0-9_-]+)\b', message, re.IGNORECASE)
    if m2:
        return m2.group(1).lower()
    # Resolve from conversation history (e.g. "assign the checklist you just created")
    recent = _extract_recent_entity_from_history(history, "checklist")
    if recent:
        return recent
    return None


def _extract_room_query(message: str, history: Optional[List[Dict[str, Any]]] = None) -> str:
    m_full = re.search(r'(room-[a-zA-Z0-9_-]+)', message, re.IGNORECASE)
    if m_full:
        return m_full.group(1)
    if "," in message:
        parts = [p.strip() for p in message.split(",") if p.strip()]
        for p in parts[1:]:
            p_clean = re.sub(r'(?i)^(?:room|suite|bay)\s*#?', '', p).strip()
            if re.match(r'^\d{2,4}$', p_clean):
                return p_clean
    m_room_num = re.search(r'(?:room|suite|bay)\s*#?\s*([0-9a-zA-Z_-]+)', message, re.IGNORECASE)
    if m_room_num:
        cand = m_room_num.group(1).strip()
        if not _is_pronoun_or_anaphor(cand):
            return cand
    m_num = re.search(r'\b(\d{3})\b', message)
    if m_num:
        return m_num.group(1)

    # Contextual reference resolution (e.g. "change that room to Occupied")
    lower = message.lower()
    if any(p in lower for p in ["that room", "the room", "that suite", "the suite", "that one", "room you created", "room you just created"]):
        recent = _extract_recent_entity_from_history(history, "room")
        if recent:
            return recent
    return ""


# Request classification shared by interceptors, result analysis and the grounding guard.
# Read-only phrasing never yields a mutation intent, and the creation target is the first object noun
# after the create verb (so "Create a checklist ... consultation room is clean" is a checklist, not a task).
_READ_ONLY_REQUEST = re.compile(
    r"^\s*(?:(?:hi|hello|hey)\b[\s,!.]*)?(?:please\s+|can\s+you\s+|could\s+you\s+)?"
    r"(?:give|gve|show|list|get|view|display|what|which|who|whom|how|tell|find|summari[sz]e|summary|are|is|do|does|any)\b"
)
_CREATE_VERB = re.compile(r"\b(?:create|add|make|schedule|register|set\s+up)\b")
_CREATE_TARGET = re.compile(
    r"\b(task|checklist|room|suite|inventory|item|supply|supplies|staff|invitation|leave)s?\b"
)
_ROOM_UPDATE_VERB = re.compile(r"\b(?:change|update|set|mark|move|switch|flag)\b")


def _is_read_only_request(message: str) -> bool:
    return bool(_READ_ONLY_REQUEST.match((message or "").lower()))


_INVENTORY_NOUN = re.compile(r"\b(?:inventory|stock|stocks|supplies|restock\w*)\b")
_INVENTORY_WRITE_VERB = re.compile(
    r"\b(?:add|create|register|update|change|set|edit|rename|adjust|increase|decrease|reduce|remove|deduct|"
    r"subtract|restock|receive|received|import|record|log|used|consumed|discard|discarded|confirm|save|approve|proceed)\b"
)
_INVENTORY_CHANGE_CLAIM = re.compile(
    r"\b(?:has|have)\s+been\s+(?:successfully\s+)?(?:created|added|updated|adjusted|imported|restocked|saved|increased|decreased|reduced)\b"
    r"|\bsuccessfully\s+(?:created|added|updated|adjusted|imported|restocked|saved)\b"
    r"|\b(?:i|we)(?:'ve|\s+have)\s+(?:created|added|updated|adjusted|imported|restocked|saved)\b"
)
_CLAIM_NEGATION = re.compile(r"\b(?:nothing|no|not|never|none|without)\b[^.\n]{0,25}$")


def _is_read_only_inventory_question(message: str) -> bool:
    """Questions (read-only phrasing, or a '?' without any write verb) must never reach inventory write tools."""
    if _is_read_only_request(message):
        return True
    lower = (message or "").lower().strip()
    return lower.endswith("?") and not _INVENTORY_WRITE_VERB.search(lower)


def _is_inventory_mutation_request(message: str) -> bool:
    if _is_read_only_inventory_question(message):
        return False
    lower = (message or "").lower()
    return bool(_INVENTORY_NOUN.search(lower) and _INVENTORY_WRITE_VERB.search(lower))


def _claims_inventory_change(text: Optional[str]) -> bool:
    lower = (text or "").lower()
    for m in _INVENTORY_CHANGE_CLAIM.finditer(lower):
        if not _CLAIM_NEGATION.search(lower[max(0, m.start() - 40):m.start()]):
            return True
    return False


_ALL_STOCKED_CLAIM = re.compile(
    r"[^.\n]*\b(?:all|every|each)\b[^.\n]{0,80}\b(?:adequately|sufficiently|well|fully|properly)?\s*stocked\b[^.\n]*[.!]?"
    r"|[^.\n]*\bno\s+(?:items?\s+(?:are|is)\s+)?(?:low[- ]stock|running\s+low|below\s+(?:their\s+)?(?:minimum\s+)?thresholds?)\b[^.\n]*[.!]?",
    re.IGNORECASE,
)
_NOT_FOUND_STATEMENT = re.compile(r"\b(?:not\s+found|no\s+(?:inventory\s+)?items?\s+match|no\s+matching|does\s+not\s+exist|doesn't\s+exist|no\s+record)", re.IGNORECASE)
_EXPLICIT_CREATE = re.compile(r"\b(?:create|register|new\s+(?:inventory\s+)?item|add\s+(?:a\s+|an\s+)?new)\b", re.IGNORECASE)


def _is_explicit_inventory_creation(message: str) -> bool:
    """Inventory items are created only when the user explicitly asks for a new item (never as a side effect of a restock)."""
    return bool(_EXPLICIT_CREATE.search(message or ""))


def _enforce_inventory_facts(reply: str, executed: List[Dict[str, Any]]) -> str:
    """
    Keeps inventory answers consistent with the latest verified get_inventory_status result:
    a searched item that was not found is stated as not found, and no 'everything is stocked' claim survives
    when the clinic has low or out-of-stock items.
    """
    reads = [t for t in executed if t.get("tool") == "get_inventory_status" and (t.get("result") or {}).get("status") == "SUCCESS"]
    if not reads:
        return reply
    inv = reads[-1]["result"]
    args = reads[-1].get("args") or {}
    corrections = []
    short = (inv.get("low_stock_count") or 0) + (inv.get("out_of_stock_count") or 0)
    if short and _ALL_STOCKED_CLAIM.search(reply or ""):
        reply = _ALL_STOCKED_CLAIM.sub("", reply).strip()
        corrections.append(
            f"{short} inventory item(s) in this clinic are at or below their minimum threshold "
            f"({inv.get('low_stock_count', 0)} low stock, {inv.get('out_of_stock_count', 0)} out of stock)."
        )
    searched = args.get("search_query") or args.get("item_id")
    if searched and not inv.get("found") and not _NOT_FOUND_STATEMENT.search(reply or ""):
        reply = f"{inv.get('message')}\n\n{reply}".strip()
    if corrections:
        reply = (reply + "\n\n" if reply else "") + "> ⚠️ **Verified correction:** " + " ".join(corrections)
    return reply


def _has_verified_inventory_write(executed: List[Dict[str, Any]]) -> bool:
    return any(
        t.get("tool") in INVENTORY_WRITE_TOOLS and t.get("tool") != "preview_inventory_import"
        and (t.get("execution_status") or t.get("status")) == "SUCCESS"
        and (t.get("persisted") or (t.get("result") or {}).get("persisted"))
        for t in executed
    )


def _creation_target(message: str) -> Optional[str]:
    """Returns 'task', 'checklist', 'room' or 'other' for creation requests, else None."""
    lower = (message or "").lower()
    verb = _CREATE_VERB.search(lower)
    if not verb:
        return None
    noun = _CREATE_TARGET.search(lower, verb.end())
    if not noun:
        return None
    target = noun.group(1)
    if target == "suite":
        return "room"
    return target if target in ("task", "checklist", "room") else "other"


def _is_task_creation_request(message: str) -> bool:
    """Detects whether a user message represents a task creation request (natural language or shorthand)."""
    lower = message.lower()
    if _is_read_only_request(message):
        return False
    target = _creation_target(message)
    if target is not None and target != "task":
        return False
    if any(k in lower for k in [
        "create task", "add task", "new task", "schedule task",
        "create a task", "schedule a task", "create a clinical task",
        "schedule a clinical task", "create a high-priority task",
        "create a high priority task", "create high-priority task",
        "create clinical task",
    ]):
        return True
    clinical_keywords = [
        "steriliz", "restock", "sanitiz", "post-op", "hygiene", "autoclave",
        "clean", "disinfect", "crash cart", "emergency cart", "turnover task"
    ]
    if any(k in lower for k in clinical_keywords):
        if any(w in lower for w in ["room", "suite", "101", "102", "103", "104", "due", "high", "medium", "low", "critical", "assign", "for ", "tomorrow"]) or "," in message:
            return True
    if "," in message:
        parts = [p.strip() for p in message.split(",") if p.strip()]
        if len(parts) >= 3:
            has_date = any(re.match(r'^\d{4}-\d{2}-\d{2}$', p) for p in parts)
            has_priority = any(p.lower() in ("high", "medium", "low", "critical") for p in parts)
            has_num = any(re.match(r'^(?:room\s*)?\d{2,4}$', p.lower()) for p in parts)
            if (has_date or has_priority) and has_num:
                return True
    return False


def _extract_create_task_args(
    message: str,
    context: SecurityContext,
    resolved_room_id: Optional[str] = None,
    resolved_staff_id: Optional[str] = None,
) -> Dict[str, Any]:
    title = "Clinical Follow-up & Task"
    priority = "Medium"
    due_date = date.today().isoformat()

    if "," in message:
        parts = [p.strip() for p in message.split(",") if p.strip()]
        if len(parts) >= 2:
            title = parts[0]
            for p in parts[1:]:
                p_lower = p.lower()
                if re.match(r'^\d{4}-\d{2}-\d{2}$', p):
                    due_date = p
                elif p_lower in ("high", "medium", "low", "critical"):
                    priority = p.capitalize()

    if title == "Clinical Follow-up & Task":
        m_title = re.search(r'(?:title|called|named|task)\s*[:"“\']\s*([^"”\']+)["”\']', message, re.IGNORECASE)
        m_titled_unquoted = re.search(r'titled\s+([^,]+?)(?:\s+(?:for|in|due)\b|\s*,|$)', message, re.IGNORECASE)
        if m_title:
            title = m_title.group(1).strip()
        elif m_titled_unquoted:
            title = m_titled_unquoted.group(1).strip()
        else:
            m_action = re.search(r'(?:to\s+)?(check\s+room\s+[0-9a-zA-Z_-]+|post-op\s+sanitization|sanitize\s+[^\.]+)', message, re.IGNORECASE)
            if m_action:
                title = m_action.group(1).strip().capitalize()
            else:
                cleaned = re.sub(r'(?i)^(please\s+)?(create|add|schedule)\s+(a\s+)?(new\s+)?(clinical\s+)?task\s*(for|to)?', '', message).strip()
                if cleaned:
                    cleaned_lower = cleaned.lower()
                    if cleaned_lower.startswith("and assign") or cleaned_lower.startswith("assign"):
                        title = "Clinical Care Duty Assignment"
                    elif cleaned_lower in ("john", "dr. sarah", "marcus", "nurse", "doctor"):
                        title = f"Clinical Care Duty for {cleaned.capitalize()}"
                    else:
                        title = cleaned.split(".")[0].split(" in ")[0].split(" for ")[0].strip() or title

    if priority == "Medium":
        if "critical" in message.lower():
            priority = "Critical"
        elif "high" in message.lower():
            priority = "High"
        elif "low" in message.lower():
            priority = "Low"

    room_id = resolved_room_id
    if not room_id:
        m_room = re.search(r'(room-[a-zA-Z0-9_-]+)', message)
        room_id = m_room.group(1) if m_room else None

    assigned_staff_id = resolved_staff_id
    if not assigned_staff_id:
        m_staff = re.search(r'(stf-[a-zA-Z0-9_-]+)', message)
        assigned_staff_id = m_staff.group(1) if m_staff else None

    m_date = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', message)
    if m_date:
        due_date = m_date.group(1)
    elif "tomorrow" in message.lower():
        due_date = (date.today() + timedelta(days=1)).isoformat()

    return {
        "title": title,
        "priority": priority,
        "due_date": due_date,
        "room_id": room_id,
        "assigned_staff_id": assigned_staff_id,
        "description": f"Autonomous task created via PractiCare AI ({context.user_role})",
    }


# ==============================================================================
# LANGGRAPH NODE IMPLEMENTATIONS
# ==============================================================================

def agent_reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node 1: Agent Reasoning
    Understands user request, validates executive data boundaries, dynamically binds
    authorized tool schemas, and utilizes real Gemini API (or deterministic mode if configured).
    """
    message = state["message"]
    context, _ = _resolve_context_and_db(state, config)
    executed_names = {t["tool"] for t in state.get("executed_tools", [])}
    current_iter = state.get("current_iteration", 0) + 1
    input_tokens = state.get("input_tokens", 0)
    output_tokens = state.get("output_tokens", 0)
    llm_latency_ms = state.get("llm_latency_ms", 0.0)

    # 1. Executive Data Protection Check
    refusal = gateway.validate_sensitive_query(message, context)
    if refusal:
        return {
            "current_iteration": current_iter,
            "tool_calls_planned": [],
            "approval_pending": None,
            "final_reply": (
                f"### 🛡️ Access Restricted by PractiCare Governance\n\n"
                f"> **{refusal}**\n\n"
                f"Operating as `{context.user_role}` in **{context.company_name}**. "
                f"Executive compensation records, physician scorecards, and private administrator evaluations "
                f"require **CLINIC_OWNER** clearance."
            ),
            "status": "blocked",
            "more_tools_needed": False,
            "agent_mode": state.get("agent_mode", "governance"),
            "model_name": state.get("model_name", "gateway-filter"),
        }

    agent_mode = (state.get("agent_mode") or os.getenv("AI_AGENT_MODE", "gemini")).lower()

    # 2. Real Gemini Mode
    if agent_mode == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return {
                "current_iteration": current_iter,
                "tool_calls_planned": [],
                "approval_pending": None,
                "final_reply": (
                    "### ⚠️ Google Gemini Configuration Error\n\n"
                    "> **Missing GOOGLE_API_KEY**: The agent is configured in `AI_AGENT_MODE=gemini`, "
                    "but no `GOOGLE_API_KEY` was found in the environment. "
                    "Please configure a valid Google API key or explicitly set `AI_AGENT_MODE=deterministic`."
                ),
                "status": "failed",
                "more_tools_needed": False,
                "agent_mode": "gemini",
                "model_name": "unconfigured",
                "metrics": {"error": "MISSING_GOOGLE_API_KEY"},
            }

        # Dynamically retrieve authorized schemas from Tool Registry for caller's role
        schemas = registry.get_schemas_for_role(context.user_role)
        if _is_read_only_inventory_question(message):
            schemas = [sc for sc in schemas if sc["function"]["name"] not in INVENTORY_WRITE_TOOLS]
        t0 = time.perf_counter()
        try:
            llm, active_model = get_gemini_llm(temperature=0.0)
            llm_with_tools = llm.bind_tools(schemas)

            today_iso = date.today().isoformat()
            system_prompt = (
                f"You are PractiCare AI, the autonomous clinical operations assistant for {context.company_name}.\n"
                f"Caller verified SecurityContext: Role={context.user_role}, Tenant={context.tenant_id}.\n"
                f"Current Reference Date: {today_iso} (YYYY-MM-DD). Resolve all relative dates (e.g. 'today', 'tomorrow', 'next week') strictly relative to {today_iso}.\n"
                f"You have access to authorized clinical tools through the internal Tool Gateway.\n"
                f"Analyze the user's operational request and call the appropriate tool(s).\n\n"
                f"ENTITY RESOLUTION PROTOCOL (ROOMS & STAFF):\n"
                f"1. When scheduling a task via 'create_clinical_task':\n"
                f"   - 'room_id' MUST be the actual database primary key (e.g. 'room-101', 'room-xxxx'), NOT display numbers like '101' or names. First call 'search_rooms' to resolve it.\n"
                f"   - 'assigned_staff_id' MUST be the actual database primary key (e.g. 'stf-001', 'stf-xxxx'), NOT natural language names like 'Dr. Sarah'. Call 'search_staff' to resolve it.\n"
                f"2. When reassigning or updating a task via 'update_task_status':\n"
                f"   - If the user names a provider (e.g. 'assign to Nurse Mark'), call 'search_staff' to resolve their database staff ID before calling 'update_task_status'.\n"
                f"   - 'task_id' must be the exact database ID (e.g. 'tsk-xxxx'). If user refers to a task by title, call 'list_tasks' to inspect and identify the task ID.\n"
                f"3. When assigning or updating a checklist via 'update_checklist':\n"
                f"   - 'checklist_id' MUST be the exact database ID (e.g. 'chk-9bf244db', 'chk-xxxx').\n"
                f"   - If the user names a staff member (e.g. 'Dr. Rachel Kim'), first call 'search_staff' to resolve their database staff ID before calling 'update_checklist'.\n"
                f"   - When assigning a checklist to a person, call 'update_checklist(checklist_id=..., assigned_staff_id=resolved_staff_id)'. DO NOT stop at search_staff!\n"
                f"4. When updating or changing room status via 'update_room':\n"
                f"   - 'room_id' MUST be the actual database primary key (e.g. 'room-101', 'room-xxxx'). If user provides a room name or number (e.g. 'Room 101' or 'Primary Exam Suite'), call 'search_rooms' to resolve it first if not known.\n"
                f"   - Call 'update_room(room_id=..., status=...)'. Valid status values are: 'Available', 'Occupied', 'Turnover'. DO NOT stop at search_rooms!\n"
                f"5. Never guess, assume, or fabricate a database primary key.\n"
                f"6. If an entity search returns 0 rooms or staff, ask the user to clarify or select a valid entity.\n"
                f"7. If an entity search returns multiple ambiguous matches, list them and ask the user to specify.\n"
                f"8. If a tool call returned an error (e.g. ROOM_NOT_FOUND), inspect recovery hints and resolve the entity before retrying.\n\n"
                f"OPERATIONAL INTENT & WORKFLOW PROTOCOL:\n"
                f"- ACTION REQUESTS (e.g. 'Create a task for John...', 'Assign checklist chk-xxx to Dr. Kim', 'Change Room 101 to Occupied', 'Complete task 15'):\n"
                f"  Resolve staff and rooms first if needed via 'search_staff' or 'search_rooms'. Call the write tool ('update_checklist', 'update_room', 'create_clinical_task', 'update_task_status'). Once done, return a concise confirmation. Do not generate reports or unsolicited analysis.\n"
                f"- RETRIEVAL REQUESTS (e.g. 'Show my pending tasks', 'Show low-stock inventory', 'Find staff', 'Checklist details', 'Room details'):\n"
                f"  Call 'list_tasks', 'get_inventory_status', 'search_staff', 'get_checklist_details', 'get_room_details', or 'get_task_details'. Return clean results without unrequested metrics or analysis.\n"
                f"- EXPLANATION REQUESTS (e.g. 'Explain task 15', 'Explain why task 15 is still pending'):\n"
                f"  Call 'list_tasks' or 'get_task_details' with task_id='tsk-15' (or the requested ID) to fetch task details, notes, and status. Base your explanation strictly on what the records document. Never invent or assume hypothetical reasons.\n"
                f"- CONCISE ANALYSIS (e.g. 'How is my team performing?'):\n"
                f"  Call 'get_team_task_performance' and return a concise operational performance summary.\n"
                f"- DETAILED ANALYSIS (e.g. 'Analyse my team's performance over the last month'):\n"
                f"  Call 'get_team_task_performance' and provide a comprehensive operational analysis of metrics, workloads, and bottlenecks.\n"
                f"- FORMAL REPORT (e.g. 'Generate a monthly team performance report'):\n"
                f"  Call 'get_team_task_performance' and/or 'get_room_turnover_status' to synthesize a full structured Markdown report.\n\n"
                f"AVAILABLE TOOLS:\n"
                f"- 'update_checklist': Assign/reassign staff or update title/category of an existing checklist. Requires checklist_id.\n"
                f"- 'get_checklist_details': Retrieve complete details of a specific checklist by ID.\n"
                f"- 'update_room': Update room status ('Available', 'Occupied', 'Turnover'), name, or room type. Requires room_id.\n"
                f"- 'get_room_details': Retrieve complete details of a specific room by database ID or room number.\n"
                f"- 'get_task_details': Retrieve full clinical task details by task ID.\n"
                f"- 'create_room': Create a new room in current clinic (CLINIC_OWNER only).\n"
                f"- 'create_checklist': Create a new checklist in current clinic.\n"
                f"- 'list_checklists': Query and filter checklists.\n"
                f"- 'create_staff_invitation': Create a staff invitation code (CLINIC_OWNER only).\n"
                f"- 'get_team_task_performance': Team completion rates, overdue tasks, bottlenecks, provider workload.\n"
                f"- 'get_room_turnover_status': Live exam/surgery room statuses and turnover counts.\n"
                f"- 'search_rooms': Resolve room numbers, names, or IDs to database room_id.\n"
                f"- 'search_staff': Resolve staff names, roles, or IDs to database staff_id.\n"
                f"- 'list_tasks': Query authorized tasks with filters (task_id, status, priority, staff, room, overdue).\n"
                f"- 'create_clinical_task': Create a new clinical task.\n"
                f"- 'update_task_status': Update task status ('Pending', 'In Progress', 'Completed'), priority, or reassign provider.\n"
                f"- 'get_inventory_status': Real inventory: stock levels, low-stock alerts, expiry (expiry_filter: expired, within_7, within_30, within_90, none; sort_by='expiry'), supplier, batch, item details.\n"
                f"- 'create_inventory_item' / 'update_inventory_item' / 'adjust_inventory_stock': Inventory writes (Owner/Manager only).\n"
                f"- 'preview_inventory_import' then 'confirm_inventory_import': Review-and-confirm import of several pasted inventory lines (Owner/Manager only).\n"
                f"- 'get_practice_summary': Overview of practice facility, task rate, staff roster, inventory alerts.\n"
                f"- 'update_checklist_status': Update or toggle completion status for sterilization/hygiene checklists.\n"
                f"- 'delete_clinical_checklist': Destructive deletion requiring human approval.\n"
                f"- 'get_operational_task_conflicts': Detects tasks/checklists assigned to staff on holiday, sick leave, or DND; staff with assigned tasks who have not logged in recently; overdue tasks; and unassigned duties.\n"
                f"- 'get_staff_availability_and_leaves': Inspects staff work status (ACTIVE, HOLIDAY, SICK_LEAVE, DND), active approved leave dates, and last login events.\n"
                f"- 'set_staff_work_status': Updates staff work status or records scheduled holiday/leave.\n"
                f"- If no tools are required, answer directly."
            )

            system_prompt += (
                "\nINVENTORY PROTOCOL:\n"
                "- For ANY inventory question (stock, quantities, availability, expiry, low stock, item details) call "
                "'get_inventory_status' first and answer only from its results. For expiry questions pass expiry_filter "
                "('expired', 'within_7', 'within_30', 'within_90', 'none') and sort_by='expiry'. Never state stock levels, "
                "expiry dates or item IDs that the tool did not return.\n"
                "- Questions never change inventory. Call inventory write tools only when the user explicitly asks to "
                "create, update, adjust or import inventory (Owner/Manager only; Doctors and Nurses are read-only).\n"
                "- Answer ONLY what the returned items support. If a searched item is not found, say exactly that it was not "
                "found and that no stock changes were made; do not add claims about other or all items. stock_status (In Stock / "
                "Low Stock / Out of Stock) and expiry_state (Expired / Expiring Soon / Valid / No Expiry Date) are separate "
                "server values; report both, never derive your own. A quantity of 0 is 'Out of Stock', not 'not found'.\n"
                "- To change an existing item, pass its exact item_id (from get_inventory_status) or item_query (its name). "
                "Use 'adjust_inventory_stock' for stock changes (positive restocks, negative reduces), 'update_inventory_item' "
                "for other fields (min threshold, expiry, supplier, batch, unit, price, room, name). If a tool returns "
                "AMBIGUOUS_ITEM, list the candidates and ask the user to choose; if NOT_FOUND, say so. Never create a new item "
                "unless the user explicitly asks to create it. Never invent missing values; ask the user for them.\n"
                "- After a write, report the actual values from the tool result (e.g. previous_stock -> new_stock, changes).\n"
                "- To import several pasted lines: call 'preview_inventory_import', show every row with its issues, and ask "
                "the user to confirm. Only after the user confirms, call 'confirm_inventory_import' with the preview's "
                "confirm_arguments (apply only corrections the user gave). For PDF or image files, tell the user to use "
                "Inventory > Import in the app.\n"
                "- Inventory updates, stock adjustments and imports wait for user approval: say they await approval, never "
                "that they are done.\n"
            )
            system_prompt += ("\nCONVERSATION & DATA GROUNDING:\n"
                "Use prior turns to resolve 'they', 'their names', 'those', 'it', and follow-up requests. "
                "Do not use those pronouns as literal search terms. "
                "For off-duty staff names use search_staff with on_shift=false and empty query. "
                "For on-shift staff use on_shift=true. "
                "For checklist questions use list_checklists or get_checklist_details. For room creation use create_room. "
                "For checklist creation use create_checklist. For staff onboarding use create_staff_invitation; "
                "never claim a staff account was created by an invitation. "
                "Only report successful writes when tool results confirm SUCCESS and persisted=true. "
                "Use multiple tools for cross-domain questions. Ask clarification only for ambiguous write targets. "
                "Never fabricate database records or results.\n")
            existing_messages = state.get("langchain_messages") or []
            if not existing_messages:
                prompt_messages = [SystemMessage(content=system_prompt)]
                for turn in (state.get("conversation_history") or [])[-12:]:
                    role = (turn.get("role") or "").lower()
                    content = str(turn.get("content") or "")[:5000]
                    if role == "user":
                        prompt_messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        prompt_messages.append(AIMessage(content=content))
                prompt_messages.append(HumanMessage(content=message))
            else:
                prompt_messages = list(existing_messages)
                if state.get("executed_tools"):
                    prompt_messages.append(
                        HumanMessage(content=(
                            "Proceed with the user's operational request using the tool outputs above.\n"
                            "- If 'search_rooms' resolved a room and user wants to update room status, immediately call 'update_room' using that exact database 'room_id' and the requested status.\n"
                            "- If 'search_rooms' resolved exactly one room and user wants to schedule a task, call 'create_clinical_task' using that exact database 'room_id'.\n"
                            "- If 'search_staff' resolved a staff member and user wants to assign a checklist, immediately call 'update_checklist' with that 'checklist_id' and the resolved 'assigned_staff_id'.\n"
                            "- If 'search_staff' resolved a staff member and user wants to assign a task, call 'update_task_status' or 'create_clinical_task'.\n"
                            "- If an entity search returned no matching rooms/staff or multiple ambiguous matches, answer directly to ask the user to clarify or select a valid entity.\n"
                            "- Do not repeat tools that already succeeded."
                        ))
                    )

            res = invoke_gemini_with_retry(llm_with_tools, prompt_messages)
            model_calls = state.get("model_calls", 0) + 1
            llm_elapsed = round((time.perf_counter() - t0) * 1000, 2)
            llm_latency_ms += llm_elapsed

            inp, out = _extract_usage(res)
            input_tokens += inp
            output_tokens += out

            def _is_duplicate_call(name: str, args: dict) -> bool:
                for ex in state.get("executed_tools", []):
                    ex_args = ex.get("args") or {}
                    # Never repeat identical call with identical arguments
                    if ex["tool"] == name and ex_args == args:
                        return True
                    # If write tool already succeeded, never repeat it
                    if ex["tool"] == name and ex.get("status") == "SUCCESS" and name in (
                        "create_clinical_task",
                        "delete_clinical_checklist",
                        "update_checklist_status",
                        "update_checklist",
                        "update_room",
                        "create_room",
                        "create_checklist",
                        "create_staff_invitation",
                        "create_inventory_item",
                        "update_inventory_item",
                        "adjust_inventory_stock",
                        "confirm_inventory_import",
                    ):
                        return True
                return False

            planned = []
            for idx, tc in enumerate(getattr(res, "tool_calls", [])):
                tc_name = tc["name"]
                tc_args = tc.get("args", {})
                tc_id = tc.get("id") or f"call_{tc_name}_{idx}"
                if not _is_duplicate_call(tc_name, tc_args):
                    planned.append({"name": tc_name, "arguments": tc_args, "call_id": tc_id})

            updated_langchain_messages = list(prompt_messages) + [res]

            if not planned:
                # 1. Autonomous Safety Interceptor (explicit write requests only; read-only requests never synthesize writes)
                request_intent = _detect_mutation_intent(message)
                # 1a. Clinical Task Creation Interceptor
                if request_intent == "task_create" and not _has_verified_task_creation(state.get("tool_results", {}), state.get("executed_tools", [])):
                    search_rooms_res = state.get("tool_results", {}).get("search_rooms")
                    room_match_count = search_rooms_res.get("match_count", 0) if search_rooms_res else 0
                    if search_rooms_res and room_match_count == 1:
                        resolved_room_id = search_rooms_res["rooms"][0]["room_id"]
                        resolved_staff_id = None
                        search_staff_res = state.get("tool_results", {}).get("search_staff")
                        if search_staff_res and search_staff_res.get("staff"):
                            active_s = [s for s in search_staff_res["staff"] if s.get("is_active")]
                            resolved_staff_id = (active_s[0] if active_s else search_staff_res["staff"][0]).get("staff_id")
                        elif _extract_staff_id(message):
                            resolved_staff_id = _extract_staff_id(message)
                        create_args = _extract_create_task_args(
                            message,
                            context,
                            resolved_room_id=resolved_room_id,
                            resolved_staff_id=resolved_staff_id,
                        )
                        planned.append({
                            "name": "create_clinical_task",
                            "arguments": create_args,
                            "call_id": "call_create_clinical_task_enforced",
                        })

                # 1b. Checklist Assignment Interceptor
                lower_m = message.lower()
                is_chk_assign = request_intent == "checklist_assign"
                if is_chk_assign and not _has_verified_checklist_update(state.get("tool_results", {}), state.get("executed_tools", [])):
                    chk_id = _extract_checklist_id(message, state.get("conversation_history"))
                    search_staff_res = state.get("tool_results", {}).get("search_staff")
                    resolved_staff_id = None
                    if search_staff_res and search_staff_res.get("staff"):
                        active_s = [s for s in search_staff_res["staff"] if s.get("is_active")]
                        resolved_staff_id = (active_s[0] if active_s else search_staff_res["staff"][0]).get("staff_id")
                    elif re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message):
                        resolved_staff_id = re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message).group(0)

                    if chk_id and resolved_staff_id:
                        planned.append({
                            "name": "update_checklist",
                            "arguments": {
                                "checklist_id": chk_id,
                                "assigned_staff_id": resolved_staff_id,
                            },
                            "call_id": "call_update_checklist_enforced",
                        })

                # 1c. Room Status Change Interceptor
                is_room_update = request_intent == "room_update"
                if is_room_update and not _has_verified_room_update(state.get("tool_results", {}), state.get("executed_tools", [])):
                    search_rooms_res = state.get("tool_results", {}).get("search_rooms")
                    resolved_room_id = None
                    m_exp = re.search(r'\broom-(?:[a-zA-Z0-9_-]+)\b', message)
                    if m_exp:
                        resolved_room_id = m_exp.group(0)
                    elif search_rooms_res and search_rooms_res.get("rooms"):
                        resolved_room_id = search_rooms_res["rooms"][0].get("room_id")

                    status_val = None
                    if "occupied" in lower_m:
                        status_val = "Occupied"
                    elif "available" in lower_m:
                        status_val = "Available"
                    elif "turnover" in lower_m:
                        status_val = "Turnover"

                    if resolved_room_id and status_val:
                        planned.append({
                            "name": "update_room",
                            "arguments": {
                                "room_id": resolved_room_id,
                                "status": status_val,
                            },
                            "call_id": "call_update_room_enforced",
                        })

                if not planned:
                    # Gemini generated direct text answer without calling tools
                    direct_reply = _extract_text_content(res.content)
                    direct_reply = _enforce_mutation_grounding(
                        direct_reply,
                        message,
                        context,
                        state.get("tool_results", {}),
                        state.get("executed_tools", []),
                        state.get("conversation_history"),
                    )
                    return {
                        "current_iteration": current_iter,
                        "tool_calls_planned": [],
                        "final_reply": direct_reply,
                        "status": "completed",
                        "more_tools_needed": False,
                        "agent_mode": "gemini",
                        "model_name": active_model,
                        "model_calls": model_calls,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "llm_latency_ms": llm_latency_ms,
                        "langchain_messages": updated_langchain_messages,
                    }

            return {
                "current_iteration": current_iter,
                "tool_calls_planned": planned,
                "more_tools_needed": len(planned) > 0,
                "agent_mode": "gemini",
                "model_name": active_model,
                "model_calls": model_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "llm_latency_ms": llm_latency_ms,
                "langchain_messages": updated_langchain_messages,
            }

        except Exception as exc:
            logger.error("Gemini reasoning failed: %s", exc)
            err_str = str(exc)
            err_code = "PROVIDER_ERROR"
            if isinstance(exc, ImportError):
                err_code = "AI_RUNTIME_MISSING"
                detail = f"AI runtime dependency is not installed on the backend ({exc}). Rebuild the backend image."
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                err_code = "429 RESOURCE_EXHAUSTED"
                detail = "Daily Gemini API request quota exceeded on Google's Free Tier. Please retry later or update your API key."
            elif "404" in err_str or "NOT_FOUND" in err_str:
                err_code = "404 NOT_FOUND"
                detail = "The requested Gemini model is not available or has been sunset by Google."
            elif "400" in err_str or "API_KEY_INVALID" in err_str or "INVALID_ARGUMENT" in err_str:
                err_code = "400 INVALID_API_KEY"
                detail = "The provided GOOGLE_API_KEY was rejected by Google GenAI."
            else:
                detail = err_str

            # In accordance with requirements: do not silently switch to deterministic mode on Gemini failure!
            return {
                "current_iteration": current_iter,
                "tool_calls_planned": [],
                "approval_pending": None,
                "final_reply": (
                    f"### ⚠️ Google Gemini Provider Error\n\n"
                    f"> **[{err_code}]:** {detail}\n\n"
                    f"Operating in mode `AI_AGENT_MODE=gemini`. "
                    f"In accordance with security governance, fallback to deterministic mode is disabled during provider errors."
                ),
                "status": "failed",
                "more_tools_needed": False,
                "agent_mode": "gemini",
                "model_name": os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
                "metrics": {"error": err_code, "detail": detail},
            }

    # 3. Deterministic Mode (Explicitly configured)
    planned = _plan_tools_deterministic(
        message=message,
        context=context,
        existing_results=state.get("tool_results", {}),
        executed_names=executed_names,
        executed_tools=state.get("executed_tools", []),
        history=state.get("conversation_history"),
    )

    return {
        "current_iteration": current_iter,
        "tool_calls_planned": planned,
        "more_tools_needed": len(planned) > 0,
        "agent_mode": "deterministic",
        "model_name": "deterministic-engine",
    }


def tool_execution_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node 2: Tool Execution
    Dispatches planned tool calls exclusively through ToolGateway.execute().
    Never accesses repositories or database models directly.
    Handles Human-In-The-Loop approvals for HIGH risk actions.
    """
    if state.get("status") == "failed":
        return {}

    planned = state.get("tool_calls_planned", [])
    context, db = _resolve_context_and_db(state, config)
    approval_id = state.get("approval_id")

    executed_tools = list(state.get("executed_tools", []))
    tool_results = dict(state.get("tool_results", {}))
    langchain_messages = list(state.get("langchain_messages") or [])
    approval_pending = None

    for call in planned:
        tool_name = call["name"]
        args = call.get("arguments", {})
        call_id = call.get("call_id") or f"call_{tool_name}"

        # Read-only questions never write inventory, and items are never created unless explicitly requested,
        # whatever the model planned
        guard = None
        if tool_name in INVENTORY_WRITE_TOOLS and _is_read_only_inventory_question(state.get("message", "")):
            guard = ("READ_ONLY_REQUEST", f"'{tool_name}' was not executed: the request is a question, and questions never change inventory.")
        elif tool_name == "create_inventory_item" and not _is_explicit_inventory_creation(state.get("message", "")):
            guard = ("CREATION_NOT_REQUESTED", "'create_inventory_item' was not executed: the user did not explicitly ask to create a new "
                     "inventory item. If the item was not found, tell the user and ask whether to create it.")
        if guard:
            result = {"error": guard[0], "detail": guard[1]}
            gateway._record_audit(
                db=db, log_id=f"aud-{uuid.uuid4().hex[:8]}", context=context, tool_name=tool_name,
                input_args=dict(args or {}), status="BLOCKED", error_detail=result["detail"],
            )
            executed_tools.append({
                "tool": tool_name, "tool_name": tool_name, "args": args, "status": "FAILED",
                "execution_status": "FAILED", "authorized": False, "is_read_only": False, "result": result,
                "resource_id": None, "tenant_id": context.tenant_id, "persisted": False, "error_code": guard[0],
            })
            tool_results[tool_name] = result
            if ToolMessage is not None:
                langchain_messages.append(ToolMessage(content=json.dumps(result), tool_call_id=call_id, name=tool_name))
            continue

        # Execute through Gateway Interceptor
        result = gateway.execute(
            tool_name=tool_name,
            arguments=args,
            context=context,
            db=db,
            approval_id=approval_id,
        )

        # Check if Human Approval is required
        if result.get("status") == "APPROVAL_REQUIRED":
            approval_pending = {
                "approval_id": result["approval_id"],
                "tool_name": tool_name,
                "description": result.get("description", "Human confirmation required."),
                "arguments": result.get("arguments", {}),
            }
            executed_tools.append({
                "tool": tool_name,
                "tool_name": tool_name,
                "args": args,
                "status": "APPROVAL_REQUIRED",
                "execution_status": "APPROVAL_REQUIRED",
                "authorized": True,
                "is_read_only": False,
                "result": result,
                "duration_ms": result.get("duration_ms"),
                "correlation_id": result.get("correlation_id"),
                "resource_id": result.get("resource_id") or result.get("task_id"),
                "tenant_id": context.tenant_id,
                "persisted": False,
                "error_code": None,
            })
            tool_results[tool_name] = result
            # Halt further execution until approved
            break

        status = "SUCCESS" if ("error" not in result and result.get("status") != "BLOCKED") else "FAILED"
        tool_meta = registry.get(tool_name)
        is_read_only = tool_meta.is_read_only if tool_meta else True
        persisted = result.get("persisted", False) if status == "SUCCESS" else False
        error_code = result.get("error") if status == "FAILED" else None
        authorized = status != "FAILED" or error_code != "FORBIDDEN"
        resource_id = (
            result.get("resource_id")
            or result.get("task_id")
            or result.get("checklist_id")
            or result.get("room_id")
            or result.get("invitation_id")
        )

        executed_tools.append({
            "tool": tool_name,
            "tool_name": tool_name,
            "args": args,
            "status": status,
            "execution_status": status,
            "authorized": authorized,
            "is_read_only": is_read_only,
            "result": result,
            "duration_ms": result.get("duration_ms"),
            "correlation_id": result.get("correlation_id"),
            "resource_id": resource_id,
            "tenant_id": context.tenant_id,
            "persisted": persisted,
            "error_code": error_code,
        })
        tool_results[tool_name] = result

        # Append structured ToolMessage for Gemini multi-step reasoning (unavailable without langchain_core)
        if ToolMessage is not None:
            langchain_messages.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call_id,
                    name=tool_name,
                )
            )

    return {
        "tool_calls_planned": [],
        "executed_tools": executed_tools,
        "tool_results": tool_results,
        "approval_pending": approval_pending,
        "langchain_messages": langchain_messages,
    }


def result_analysis_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node 3: Result Analysis
    Inspects tool execution results, evaluates room search outcomes, enables error recovery
    via read-only corrective tools, and asks for clarification/selection when needed.
    """
    if state.get("status") in ("failed", "blocked") or state.get("approval_pending"):
        return {"more_tools_needed": False}

    current_iter = state.get("current_iteration", 0)
    executed_tools = state.get("executed_tools", [])
    executed_names = {t["tool"] for t in executed_tools}
    tool_results = state.get("tool_results", {})
    context, _ = _resolve_context_and_db(state, config)
    message = state.get("message", "")

    # If a requested write tool completed and was verified, finish workflow
    if _is_task_creation_request(message) and _has_verified_task_creation(tool_results, executed_tools):
        return {"more_tools_needed": False, "status": "completed"}
    request_intent = _detect_mutation_intent(message)
    if request_intent in ("checklist_assign", "checklist_update") and _has_verified_checklist_update(tool_results, executed_tools):
        return {"more_tools_needed": False, "status": "completed"}
    if request_intent == "room_update" and _has_verified_room_update(tool_results, executed_tools):
        return {"more_tools_needed": False, "status": "completed"}
    if any(t.get("tool") in ("create_room", "create_checklist", "create_staff_invitation", "delete_clinical_checklist",
                             "create_inventory_item", "update_inventory_item", "adjust_inventory_stock", "confirm_inventory_import")
           and t.get("status") == "SUCCESS" for t in executed_tools):
        return {"more_tools_needed": False, "status": "completed"}

    if current_iter >= MAX_ITERATIONS or len(executed_names) >= MAX_TOTAL_TOOLS:
        return {"more_tools_needed": False, "status": "completed"}

    # 1. Zero-match & Ambiguity Evaluation (Rooms & Staff)
    if "search_rooms" in tool_results:
        sr = tool_results["search_rooms"]
        m_count = sr.get("match_count", 0)
        query_val = sr.get("query", "")
        rooms = sr.get("rooms", [])

        # If no matching room exists, ask user to select a valid room rather than attempting task creation
        if m_count == 0 and _is_task_creation_request(message):
            failed_ct = any(t["tool"] == "create_clinical_task" and t["status"] == "FAILED" for t in executed_tools)
            intercept_header = (
                f"### ⚠️ Action Intercepted by PractiCare Governance\n\n"
                f"> **Error [EXECUTION_ERROR]:** Room ID '{query_val}' not found in tenant '{context.tenant_id}'.\n\n"
            ) if failed_ct else ""
            return {
                "more_tools_needed": False,
                "status": "completed",
                "final_reply": (
                    f"{intercept_header}"
                    f"### 🔍 Room Not Found in Clinic Partition\n\n"
                    f"No room matching **\"{query_val}\"** was found in tenant `{context.tenant_id}`.\n\n"
                    f"Please verify the room number or select a valid room from your clinic partition before scheduling this clinical task."
                ),
            }

        # If multiple rooms match, ask for clarification unless already written
        if m_count > 1 and _is_task_creation_request(message):
            task_executed = any(t["tool"] == "create_clinical_task" and t["status"] == "SUCCESS" for t in executed_tools)
            if not task_executed:
                room_lines = [f"- **{r.get('display_label')}**" for r in rooms]
                return {
                    "more_tools_needed": False,
                    "status": "completed",
                    "final_reply": (
                        f"### ❓ Clarification Required — Multiple Rooms Match\n\n"
                        f"Multiple rooms in tenant `{context.tenant_id}` match your query **\"{query_val}\"**:\n\n"
                        + "\n".join(room_lines) + "\n\n"
                        f"Please clarify which specific room number or ID this task should be assigned to."
                    ),
                }

    if "search_staff" in tool_results:
        stf = tool_results["search_staff"]
        m_count = stf.get("match_count", 0)
        query_val = stf.get("query", "")
        staff_members = stf.get("staff", [])

        if m_count == 0 and _is_task_creation_request(message):
            return {
                "more_tools_needed": False,
                "status": "completed",
                "final_reply": (
                    f"### 🔍 Staff Member Not Found\n\n"
                    f"No clinical staff matching **\"{query_val}\"** was found in tenant `{context.tenant_id}`.\n\n"
                    f"Please verify the provider name or check the staff directory before assigning this clinical task."
                ),
            }

        if m_count > 1 and _is_task_creation_request(message):
            lower = message.lower()
            is_auto_assign = any(w in lower for w in ["appropriate", "on-duty", "active", "available", "anyone on shift", "on shift", "nurse", "doctor"]) or not query_val
            has_written = any(t["tool"] in ("create_clinical_task", "update_task_status") and t["status"] == "SUCCESS" for t in executed_tools)
            if not is_auto_assign and not has_written:
                staff_lines = [f"- **{s.get('display_label')}**" for s in staff_members]
                return {
                    "more_tools_needed": False,
                    "status": "completed",
                    "final_reply": (
                        f"### ❓ Clarification Required — Multiple Providers Match\n\n"
                        f"Multiple staff members in tenant `{context.tenant_id}` match query **\"{query_val}\"**:\n\n"
                        + "\n".join(staff_lines) + "\n\n"
                        f"Please clarify which specific provider ID this task should be assigned to."
                    ),
                }

    # 2. Progress toward Write Action if Entities are Resolved
    lower = message.lower()
    wants_action = _is_task_creation_request(message) or any(w in lower for w in ["reassign", "assign to", "change task", "update task"])
    has_written = any(t["tool"] in ("create_clinical_task", "update_task_status") and t["status"] == "SUCCESS" for t in executed_tools)

    if wants_action and not has_written:
        has_room_res = "search_rooms" in tool_results and tool_results["search_rooms"].get("match_count", 0) >= 1
        has_staff_res = "search_staff" in tool_results and tool_results["search_staff"].get("match_count", 0) >= 1
        if has_room_res or has_staff_res:
            return {"more_tools_needed": True, "status": "in_progress"}

    wants_checklist_action = request_intent in ("checklist_assign", "checklist_update")
    if wants_checklist_action and not _has_verified_checklist_update(tool_results, executed_tools):
        has_staff_res = "search_staff" in tool_results and tool_results["search_staff"].get("match_count", 0) >= 1
        chk_id = _extract_checklist_id(message, state.get("conversation_history"))
        if has_staff_res or chk_id:
            return {"more_tools_needed": True, "status": "in_progress"}

    wants_room_action = request_intent == "room_update"
    if wants_room_action and not _has_verified_room_update(tool_results, executed_tools):
        has_room_res = "search_rooms" in tool_results and tool_results["search_rooms"].get("match_count", 0) >= 1
        m_explicit_room = re.search(r'\broom-(?:[a-zA-Z0-9_-]+)\b', message)
        if has_room_res or m_explicit_room:
            return {"more_tools_needed": True, "status": "in_progress"}

    # 3. Validation Error Recovery (Rooms & Staff)
    ct_execs = [t for t in executed_tools if t["tool"] in ("create_clinical_task", "update_task_status")]
    if ct_execs:
        last_ct = ct_execs[-1]
        if last_ct["status"] == "FAILED":
            ct_res = last_ct.get("result", {})
            err_type = ct_res.get("error_type")
            detail = str(ct_res.get("detail", ""))
            if err_type == "ROOM_NOT_FOUND" or ("Room ID" in detail and "not found" in detail):
                if "search_rooms" not in executed_names and current_iter < MAX_ITERATIONS:
                    logger.info("Task operation failed with room error. Triggering recovery via search_rooms.")
                    return {"more_tools_needed": True, "status": "in_progress"}
            if "Staff ID" in detail and "not found" in detail:
                if "search_staff" not in executed_names and current_iter < MAX_ITERATIONS:
                    logger.info("Task operation failed with staff error. Triggering recovery via search_staff.")
                    return {"more_tools_needed": True, "status": "in_progress"}

    # 4. Deterministic Mode multi-step checks
    agent_mode = state.get("agent_mode", "gemini")
    if agent_mode == "deterministic":
        lower = message.lower()
        needs_rooms = (
            ("room" in lower or "facility" in lower or "turnover" in lower or "operations" in lower)
            and "get_room_turnover_status" not in executed_names
        )
        if needs_rooms:
            return {"more_tools_needed": True, "status": "in_progress"}

        needs_checklist_write = (
            "checklist" in lower
            and any(w in lower for w in ["assign", "reassign", "assigned to"])
            and "update_checklist" not in executed_names
        )
        if needs_checklist_write:
            return {"more_tools_needed": True, "status": "in_progress"}

        needs_room_write = (
            ("room" in lower or "suite" in lower)
            and any(w in lower for w in ["change", "occupied", "available", "turnover"])
            and "update_room" not in executed_names
        )
        if needs_room_write:
            return {"more_tools_needed": True, "status": "in_progress"}

    return {
        "more_tools_needed": False,
        "status": "completed",
    }



def report_synthesis_node(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node 4: Report Synthesis
    Synthesizes an executive Markdown report grounded in evidence from ToolGateway results.
    Uses Gemini when in Gemini mode, or verified deterministic report when configured.
    """
    tool_results = state.get("tool_results", {})
    executed = state.get("executed_tools", [])
    context, _ = _resolve_context_and_db(state, config)

    if state.get("final_reply"):
        reply = state["final_reply"]
        reply = _enforce_mutation_grounding(reply, state["message"], context, tool_results, executed, state.get("conversation_history"))
        return {
            "final_reply": reply,
            "status": state.get("status", "completed"),
            "metrics": state.get("metrics", {}),
        }

    approval_pending = state.get("approval_pending")
    agent_mode = state.get("agent_mode", "gemini")
    model_name = state.get("model_name", DEFAULT_GEMINI_MODEL)
    input_tokens = state.get("input_tokens", 0)
    output_tokens = state.get("output_tokens", 0)
    llm_latency_ms = state.get("llm_latency_ms", 0.0)

    # 1. Pending Approval notice
    if approval_pending:
        appr_id = approval_pending["approval_id"]
        t_name = approval_pending["tool_name"]
        args_str = json.dumps(approval_pending.get("arguments", {}), indent=2)
        description = approval_pending.get("description") or ""
        summary = ("\n".join(f"> {line}" for line in description.splitlines()) + "\n\n") if description else ""
        reply = (
            f"### ⚠️ Human Authorization Required\n\n"
            f"The requested action `{t_name}` requires explicit human confirmation before execution. Nothing has been written yet.\n\n"
            f"{summary}"
            f"- **Action:** Permanently execute `{t_name}`\n"
            f"- **Approval Token:** `{appr_id}`\n"
            f"- **Target Partition:** Tenant `{context.tenant_id}`\n"
            f"- **Target Parameters:**\n```json\n{args_str}\n```\n\n"
            f"Please review the parameters above and confirm approval to proceed."
        )
        return {
            "final_reply": reply,
            "status": "approval_required",
        }

    # 2. Check for unrecovered security / gateway failures in executed tools
    for ex in reversed(executed):
        res = ex.get("result", {})
        tool_name = ex.get("tool")
        if "error" in res:
            # If this tool was re-executed and succeeded, or task was created, skip
            latest_res = tool_results.get(tool_name, {})
            if latest_res.get("status") == "SUCCESS" or "action" in latest_res:
                continue
            if tool_name == "create_clinical_task" and tool_results.get("create_clinical_task", {}).get("status") == "SUCCESS":
                continue
            err_code = res.get("error")
            err_detail = res.get("detail", "Operation blocked by security governance.")
            return {
                "final_reply": (
                    f"### ⚠️ Action Intercepted by PractiCare Governance\n\n"
                    f"> **Error [{err_code}]:** {err_detail}\n\n"
                    f"- **Caller Role:** `{context.user_role}`\n"
                    f"- **Tenant Partition:** `{context.tenant_id}`\n\n"
                    f"This boundary is enforced at the Tool Gateway layer. The event has been audited."
                ),
                "status": "completed",
            }


    # 3. Real Gemini Synthesis
    if agent_mode == "gemini" and tool_results:
        t0 = time.perf_counter()
        try:
            llm, active_model = get_gemini_llm(temperature=0.0)
            synthesis_prompt = [
                SystemMessage(content=(
                    f"You are PractiCare AI, the clinical operations intelligence agent for {context.company_name}.\n"
                    f"Operating under verified SecurityContext: Role={context.user_role}, Tenant={context.tenant_id}.\n"
                    f"Tool evidence: every Tool Gateway call made for this request, in order, with its arguments and real database result:\n"
                    f"{json.dumps(_tool_evidence(executed), default=str)}\n\n"
                    f"Respond appropriately to the user's request: '{state['message']}'.\n\n"
                    f"STRICT INTENT & RESPONSE FORMAT RULES:\n"
                    f"1. ACTION REQUEST (Task created, updated, completed, or deleted):\n"
                    f"   - Return a SHORT, CLEAR confirmation with key details (Task/Checklist ID, Title, Status, Assignee, Room, Due Date).\n"
                    f"   - DO NOT generate a performance report or unsolicited analysis.\n"
                    f"2. RETRIEVAL REQUEST (Listing tasks, showing inventory, searching staff):\n"
                    f"   - Present the requested data clearly (e.g. structured bullet list or clean table).\n"
                    f"   - DO NOT attach unsolicited executive summaries or strategic recommendations.\n"
                    f"3. EXPLANATION REQUEST (Explain task, explain why a task is pending):\n"
                    f"   - Explain the exact status, assignee, room, and clinical description based STRICTLY on the retrieved records.\n"
                    f"   - State the factual reason documented in the record. DO NOT invent or assume hypothetical reasons.\n"
                    f"4. CONCISE ANALYSIS REQUEST ('How is my team performing?'):\n"
                    f"   - Provide a concise summary of team task metrics (completion rate, active tasks, provider workloads, bottlenecks).\n"
                    f"5. DETAILED ANALYSIS REQUEST ('Analyse my team's performance'):\n"
                    f"   - Provide a detailed operational analysis with workload distribution, overdue bottlenecks, and evidence-based insights.\n"
                    f"6. FORMAL REPORT REQUEST ('Generate a monthly task report', 'Create a performance report'):\n"
                    f"   - Synthesize a comprehensive, formal Markdown report with executive KPIs, room status, provider workload tables, and recommendations.\n\n"
                    f"RULES:\n"
                    f"1. Use ONLY the real factual metrics, task counts, and numbers present in the tool evidence.\n"
                    f"2. Never fabricate task counts, completion percentages, employee workloads, or room availability.\n"
                    f"3. When the same tool was called several times, combine ALL of its results (e.g. Pending and In Progress task lists).\n"
                    f"4. Quote record IDs exactly as they appear in the tool evidence. Never invent, guess or reformat an ID.\n"
                    f"5. A write succeeded only if its tool status is SUCCESS. Report failures and their reason truthfully.\n"
                    f"6. If a tool result contains a 'note', tell the user (for example, data that could not be stored).\n"
                    f"7. If role is CLINICAL_AUDITOR, ensure zero employee PII is mentioned.\n"
                    f"8. Add analysis, summaries or recommendations ONLY when the user asked for analysis or a report, whatever the role."
                )),
                HumanMessage(content=(
                    "Recent conversation context (use only to resolve references, never as evidence of current database state):\n"
                    + json.dumps((state.get("conversation_history") or [])[-10:], default=str)[:10000]
                    + "\nCurrent user request: " + state["message"]
                ))
            ]
            synth_res = invoke_gemini_with_retry(llm, synthesis_prompt)
            model_calls = state.get("model_calls", 0) + 1
            llm_elapsed = round((time.perf_counter() - t0) * 1000, 2)
            llm_latency_ms += llm_elapsed
            inp, out = _extract_usage(synth_res)
            input_tokens += inp
            output_tokens += out
            reply = _extract_text_content(synth_res.content)
            reply = _enforce_mutation_grounding(reply, state["message"], context, tool_results, executed, state.get("conversation_history"))
            return {
                "final_reply": reply,
                "status": "completed",
                "model_calls": model_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "llm_latency_ms": llm_latency_ms,
            }
        except Exception as exc:
            logger.warning("Gemini report synthesis encountered an issue: %s", exc)
            # If Gemini fails during synthesis, report provider error clearly
            reply = (
                f"### ⚠️ Google Gemini Synthesis Error\n\n"
                f"> **[PROVIDER_ERROR]**: {exc}\n\n"
                f"Falling back to verified deterministic report representation:\n\n"
                + _synthesize_markdown_report(state["message"], context, tool_results, executed)
            )
            reply = _enforce_mutation_grounding(reply, state["message"], context, tool_results, executed, state.get("conversation_history"))
            return {
                "final_reply": reply,
                "status": "completed",
            }

    # 4. Deterministic Synthesis
    reply = _synthesize_markdown_report(state["message"], context, tool_results, executed)
    reply = _enforce_mutation_grounding(reply, state["message"], context, tool_results, executed, state.get("conversation_history"))
    return {
        "final_reply": reply,
        "status": "completed",
    }


# ==============================================================================
# DETERMINISTIC PLANNING & SYNTHESIS HELPERS
# ==============================================================================

def _deterministic_expiry_filter(lower: str) -> Optional[str]:
    if "expir" not in lower and "expiry" not in lower:
        return None
    if re.search(r"\bno\s+expiry\b|\bwithout\s+(?:an?\s+)?expiry\b", lower):
        return "none"
    if re.search(r"\balready\s+expired\b|\bexpired\b", lower) and not re.search(r"\bexpir(?:e|es|ing)\b", lower):
        return "expired"
    for days in (7, 30, 90):
        if re.search(rf"\b{days}\s*days?\b", lower):
            return f"within_{days}"
    if "this week" in lower or "next week" in lower:
        return "within_7"
    if "this month" in lower or "next month" in lower or "soon" in lower:
        return "within_30"
    return None


def _plan_tools_deterministic(
    message: str,
    context: SecurityContext,
    existing_results: Dict[str, Any],
    executed_names: set,
    executed_tools: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Determines tools based on operational intent and context."""
    lower = message.lower()
    planned = []
    executed_tools = executed_tools or []

    # 1. Checklist Deletion (HIGH RISK)
    if ("delete" in lower or "remove" in lower) and "checklist" in lower:
        if "delete_clinical_checklist" not in executed_names:
            chk_id = _extract_checklist_id(message, history=history)
            planned.append({
                "name": "delete_clinical_checklist",
                "arguments": {"checklist_id": chk_id},
            })
            return planned

    # 2. Checklist Assignment (update_checklist)
    is_assign_intent = bool(re.search(r'\b(?:assign|reassign|assigned\s+to)\b', lower)) and not bool(re.search(r'\b(?:tick|untick|toggle|mark\s+completed|mark\s+done)\b', lower))
    if "checklist" in lower and is_assign_intent:
        if any(ex.get("tool") == "update_checklist" and ex.get("status") == "SUCCESS" for ex in executed_tools):
            return []
        chk_id = _extract_checklist_id(message, history=history)
        staff_q = _extract_staff_query(message, history=history)
        m_explicit_stf = re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message)

        if staff_q and not m_explicit_stf and "search_staff" not in executed_names:
            planned.append({
                "name": "search_staff",
                "arguments": {"query": staff_q},
            })
            return planned

        resolved_staff_id = m_explicit_stf.group(0) if m_explicit_stf else None
        if not resolved_staff_id and "search_staff" in existing_results:
            stf_items = existing_results["search_staff"].get("staff", [])
            if stf_items:
                active_s = [s for s in stf_items if s.get("is_active")]
                resolved_staff_id = (active_s[0] if active_s else stf_items[0]).get("staff_id")

        if chk_id and resolved_staff_id:
            planned.append({
                "name": "update_checklist",
                "arguments": {
                    "checklist_id": chk_id,
                    "assigned_staff_id": resolved_staff_id,
                },
            })
            return planned

    # 3. Room Status Change (update_room)
    if ("room" in lower or "suite" in lower) and any(w in lower for w in ["change", "status", "occupied", "available", "turnover", "update", "set"]) and not any(w in lower for w in ["create", "add new", "task", "turnover status", "turnovers"]):
        if any(ex.get("tool") == "update_room" and ex.get("status") == "SUCCESS" for ex in executed_tools):
            return []
        m_explicit_room = re.search(r'\broom-(?:[a-zA-Z0-9_-]+)\b', message)
        room_q = _extract_room_query(message, history=history)
        needs_room_search = room_q and not m_explicit_room and "search_rooms" not in executed_names

        if needs_room_search:
            planned.append({
                "name": "search_rooms",
                "arguments": {"query": room_q},
            })
            return planned

        resolved_room_id = m_explicit_room.group(0) if m_explicit_room else None
        if not resolved_room_id and "search_rooms" in existing_results:
            rooms = existing_results["search_rooms"].get("rooms", [])
            if rooms:
                resolved_room_id = rooms[0].get("room_id")

        status_val = None
        if "occupied" in lower:
            status_val = "Occupied"
        elif "available" in lower:
            status_val = "Available"
        elif "turnover" in lower:
            status_val = "Turnover"

        if resolved_room_id and status_val:
            planned.append({
                "name": "update_room",
                "arguments": {
                    "room_id": resolved_room_id,
                    "status": status_val,
                },
            })
            return planned

    # 4. Detail Read-Back Queries & Checklist Operations
    if "checklist" in lower and not bool(re.search(r'\b(?:delete|remove|create|add\s+checklist)\b', lower)) and not is_assign_intent:
        chk_id = _extract_checklist_id(message, history=history)
        is_toggle = bool(re.search(r'\b(?:update|complete|mark|toggle|tick|untick|check|uncheck)\b', lower))
        if is_toggle:
            if not chk_id and "list_checklists" in existing_results:
                chks = existing_results["list_checklists"].get("checklists", [])
                pending_chks = [c for c in chks if not c.get("is_completed")]
                if pending_chks:
                    chk_id = pending_chks[0].get("checklist_id")
                elif chks:
                    chk_id = chks[0].get("checklist_id")

            if not chk_id and "list_checklists" not in executed_names:
                planned.append({
                    "name": "list_checklists",
                    "arguments": {"my_checklists_only": True},
                })
                return planned

            if chk_id and "update_checklist_status" not in executed_names:
                is_completed = not any(w in lower for w in ["incomplete", "false", "uncheck", "untick"])
                planned.append({
                    "name": "update_checklist_status",
                    "arguments": {"checklist_id": chk_id, "is_completed": is_completed},
                })
                return planned

        if chk_id and any(w in lower for w in ["detail", "details", "view checklist", "show checklist", "get checklist"]):
            if "get_checklist_details" not in executed_names:
                planned.append({
                    "name": "get_checklist_details",
                    "arguments": {"checklist_id": chk_id},
                })
                return planned

        if not chk_id and any(w in lower for w in ["show", "list", "view", "my checklist", "what checklist", "checklists", "all checklist"]):
            if "list_checklists" not in executed_names:
                my_chks = any(w in lower for w in ["my", "assigned to me", "mine"])
                planned.append({
                    "name": "list_checklists",
                    "arguments": {"my_checklists_only": my_chks},
                })
                return planned

    if ("room" in lower or "suite" in lower) and any(w in lower for w in ["detail", "details of room", "room details", "view room", "show room"]):
        if "get_room_details" not in executed_names:
            r_id = _extract_room_query(message, history=history)
            if r_id:
                planned.append({
                    "name": "get_room_details",
                    "arguments": {"room_id": r_id},
                })
                return planned

    if "task" in lower and any(w in lower for w in ["detail", "details of task", "task details"]):
        if "get_task_details" not in executed_names:
            t_id = _extract_task_id(message, history=history)
            if t_id:
                planned.append({
                    "name": "get_task_details",
                    "arguments": {"task_id": t_id},
                })
                return planned

    # 6. Explanation Request (Explain task 15 / why task 15 is pending)
    if any(k in lower for k in ["explain", "why is", "why are", "reason for"]):
        if "list_tasks" not in executed_names:
            t_id = _extract_task_id(message, history=history)
            planned.append({
                "name": "list_tasks",
                "arguments": {"task_id": t_id},
            })
            return planned

    # 4. Create Clinical Task & Dynamic Entity Resolution (Rooms & Staff)
    is_list_or_view = any(k in lower for k in ["list", "show", "view", "pending", "all tasks", "overdue", "performance", "report", "explain", "why"])
    if _is_task_creation_request(message) and not is_list_or_view:
        # If create_clinical_task already succeeded, don't recreate
        if any(ex.get("tool") == "create_clinical_task" and ex.get("status") == "SUCCESS" for ex in executed_tools):
            return []

        search_staff_res = existing_results.get("search_staff")
        search_room_res = existing_results.get("search_rooms")

        # Step 4a: Staff Resolution
        staff_q = _extract_staff_query(message)
        is_auto_assign = any(w in lower for w in ["appropriate", "on-duty", "active", "available", "anyone on shift", "on shift"])
        needs_staff_search = (staff_q or is_auto_assign) and "search_staff" not in executed_names and not re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message)

        if needs_staff_search:
            planned.append({
                "name": "search_staff",
                "arguments": {"query": staff_q if not is_auto_assign else ""},
            })
            return planned

        # Step 4b: Room Resolution
        m_explicit_db_id = re.search(r'\broom-(?:[a-zA-Z0-9_-]+)\b', message)
        room_q = _extract_room_query(message)
        needs_room_search = room_q and not m_explicit_db_id and "search_rooms" not in executed_names

        if needs_room_search:
            planned.append({
                "name": "search_rooms",
                "arguments": {"query": room_q},
            })
            return planned

        # Step 4c: Resolving entities for task creation
        resolved_staff_id = None
        if search_staff_res:
            staff_items = search_staff_res.get("staff", [])
            if staff_items:
                active_staff = [s for s in staff_items if s.get("is_active")]
                chosen = active_staff[0] if active_staff else staff_items[0]
                resolved_staff_id = chosen.get("staff_id")
        elif re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message):
            resolved_staff_id = re.search(r'\bstf-[a-zA-Z0-9_-]+\b', message).group(0)

        resolved_room_id = None
        if m_explicit_db_id:
            resolved_room_id = m_explicit_db_id.group(0)
        elif search_room_res:
            rooms = search_room_res.get("rooms", [])
            if rooms:
                resolved_room_id = rooms[0].get("room_id")

        args = _extract_create_task_args(message, context, resolved_room_id=resolved_room_id, resolved_staff_id=resolved_staff_id)
        planned.append({
            "name": "create_clinical_task",
            "arguments": args,
        })
        return planned

    # 5. Update Task Status / Complete Task
    is_task_action = (
        any(k in lower for k in ["complete task", "mark task", "update task", "reassign task", "mark completed", "as completed", "mark as completed", "complete my assigned task", "complete assigned task", "complete my task"])
        or bool(re.search(r'\bcomplete\s+(?:the\s+)?task\b', lower))
        or bool(re.search(r'\bcomplete\s+(?:tsk-|#|\d+)', lower))
        or ("complete" in lower and "assigned task" in lower)
    )
    if is_task_action and not any(k in lower for k in ["practice summary", "clinic summary", "overview", "complete clinic", "complete practice"]):
        t_id = _extract_task_id(message)
        if not t_id and "list_tasks" in existing_results:
            lt_items = existing_results["list_tasks"].get("tasks", [])
            pending_items = [t for t in lt_items if str(t.get("status", "")).lower() == "pending"]
            if pending_items:
                t_id = pending_items[0].get("task_id")
            elif lt_items:
                t_id = lt_items[0].get("task_id")

        if not t_id and "list_tasks" not in executed_names:
            planned.append({
                "name": "list_tasks",
                "arguments": {
                    "status": "Pending",
                    "my_tasks_only": True,
                },
            })
            return planned

        if "update_task_status" not in executed_names and t_id:
            stf_id = _extract_staff_id(message)
            status_val = "Completed" if ("complete" in lower or "completed" in lower) else None
            planned.append({
                "name": "update_task_status",
                "arguments": {
                    "task_id": t_id,
                    "status": status_val,
                    "assigned_staff_id": stf_id,
                },
            })
            return planned

    # 6. List Tasks (Pending, Overdue, Assigned to Me, or General)
    if any(k in lower for k in ["list task", "show task", "view task", "my task", "my tasks", "assigned task", "assigned to me", "pending task", "overdue task", "find overdue", "find task", "overdue", "all tasks", "pending"]) and not any(k in lower for k in ["performance", "report", "create"]):
        if "list_tasks" not in executed_names:
            status_filter = "Pending" if "pending" in lower else None
            overdue_only = "overdue" in lower
            my_tasks = any(k in lower for k in ["my task", "my tasks", "assigned task", "assigned to me", "mine"])
            planned.append({
                "name": "list_tasks",
                "arguments": {
                    "status": status_filter,
                    "overdue_only": overdue_only,
                    "my_tasks_only": my_tasks,
                },
            })
            return planned

    # 6b. Operational Task Conflicts & Bottlenecks
    if any(k in lower for k in ["conflict", "conflicts", "operational conflict", "holiday conflict", "sick leave conflict", "dnd conflict", "bottleneck", "bottlenecks"]):
        if "get_operational_task_conflicts" not in executed_names:
            planned.append({
                "name": "get_operational_task_conflicts",
                "arguments": {},
            })
            return planned

    # 6c. Team Task Progress
    if any(k in lower for k in ["team task progress", "task progress", "team progress"]):
        if "get_team_task_performance" not in executed_names:
            planned.append({
                "name": "get_team_task_performance",
                "arguments": {},
            })
            return planned

    # 7. Inventory Status (read-only; deterministic mode never writes inventory)
    if any(k in lower for k in ["inventory", "supplies", "stock", "low stock", "low-stock", "running low", "out of stock", "expir"]):
        if "get_inventory_status" not in executed_names:
            inv_args: Dict[str, Any] = {"low_stock_only": any(k in lower for k in ["low", "low-stock", "running low", "out of stock"])}
            expiry_filter = _deterministic_expiry_filter(lower)
            if expiry_filter:
                inv_args["expiry_filter"] = expiry_filter
                inv_args["sort_by"] = "expiry"
            planned.append({
                "name": "get_inventory_status",
                "arguments": inv_args,
            })
            return planned

    # 8. Staff Search / Resolution
    if any(k in lower for k in ["search staff", "search for staff", "staff member", "find staff", "find dr", "find nurse", "who is on shift", "lookup staff", "staff directory", "staff list"]):
        if "search_staff" not in executed_names:
            planned.append({
                "name": "search_staff",
                "arguments": {"query": _extract_staff_query(message)},
            })
            return planned

    # 9. Room Search / Resolution
    if ("search room" in lower or "find room" in lower or "resolve room" in lower or "lookup room" in lower):
        if "search_rooms" not in executed_names:
            room_q = _extract_room_query(message)
            planned.append({
                "name": "search_rooms",
                "arguments": {"query": room_q or message},
            })
            return planned

    # 10. Room Turnover Status
    if ("room" in lower and ("turnover" in lower or "status" in lower or "cleaning" in lower or "occupied" in lower)) and not ("performance" in lower or "workload" in lower or "create" in lower):
        if "get_room_turnover_status" not in executed_names:
            planned.append({
                "name": "get_room_turnover_status",
                "arguments": {},
            })
            return planned

    # 11. Practice Summary
    if any(k in lower for k in ["practice summary", "clinic summary", "clinic overview", "practice overview", "how is my clinic performing", "how my clinic is performing"]):
        if "get_practice_summary" not in executed_names:
            planned.append({
                "name": "get_practice_summary",
                "arguments": {},
            })
            return planned

    # 12. Team Task Performance & Combined Operational Reports
    if any(k in lower for k in ["performance", "team performance", "task report", "performance report", "operational report", "workload", "team progress", "efficiency", "metrics"]):
        if "get_team_task_performance" not in executed_names:
            planned.append({
                "name": "get_team_task_performance",
                "arguments": {},
            })
        elif any(k in lower for k in ["report", "operational", "facility", "turnover", "room", "attention"]) and "get_room_turnover_status" not in executed_names:
            planned.append({
                "name": "get_room_turnover_status",
                "arguments": {},
            })
    elif any(k in lower for k in ["report", "operational", "facility", "turnover", "room status", "attention"]):
        if "get_room_turnover_status" not in executed_names:
            planned.append({
                "name": "get_room_turnover_status",
                "arguments": {},
            })

    return planned


def _detect_user_intent(message: str) -> str:
    lower = message.lower()

    # 1. Report Request (explicit request for a formal report)
    if any(k in lower for k in ["generate a report", "generate report", "create a report", "create report", "monthly report", "task report", "performance report", "weekly report", "audit report", "summary report", "generate a monthly", "full operational report", "executive task performance"]):
        return "report"
    if "report" in lower and not any(k in lower for k in ["lab report", "blood report", "pathology report", "panel labs", "review"]):
        return "report"

    # 2. Explanation Request (why, explain, reason)
    if any(k in lower for k in ["explain", "why is", "why are", "reason for", "what is the reason", "details of task"]):
        return "explanation"

    # 3. Action Request (create, schedule, complete, update, mark, toggle, delete)
    if _is_task_creation_request(message):
        return "action"

    is_task_or_item_action = (
        any(k in lower for k in ["create", "schedule", "add task", "complete task", "mark completed", "mark as completed", "update task", "reassign", "delete checklist", "remove checklist", "toggle", "tick", "untick", "update checklist", "complete checklist", "mark checklist", "change room", "update room"])
        or bool(re.search(r'\b(?:complete|tick|untick|mark|update)\s+(?:the\s+)?(?:task|checklist)\b', lower))
        or bool(re.search(r'\b(?:complete|tick|untick)\s+(?:tsk-|chk-|check-|#|\d+)', lower))
    )
    if is_task_or_item_action and not any(k in lower for k in ["how to", "should i", "practice summary", "clinic summary", "complete clinic", "complete practice"]):
        return "action"

    # 4. Detailed Analysis Request (analyse, detailed, in-depth)
    if any(k in lower for k in ["analyse", "analyze", "detailed analysis", "in-depth", "over the last month", "deep dive", "workload breakdown"]):
        return "detailed_analysis"

    # 5. Concise Analysis Request (how is my team performing, team performance overview)
    if any(k in lower for k in ["how is my team performing", "how my team is performing", "how is the team doing", "team performance", "how are we performing"]):
        return "concise_analysis"

    # 6. Retrieval Request (show, list, view, find, search, get, check, practice summary, who, which, holiday, conflict, leave)
    if any(k in lower for k in [
        "show", "list", "view", "find", "search", "lookup", "display", "what are",
        "which", "who", "holiday", "leave", "conflict", "conflicts", "dnd", "sick",
        "unavailable", "working on", "due tomorrow", "due in", "responsible",
        "inventory", "pending tasks", "overdue tasks", "low-stock", "supplies",
        "practice summary", "clinic summary", "practice overview", "clinic overview"
    ]):
        return "retrieval"

    return "concise_analysis"


def _synthesize_markdown_report(
    message: str,
    context: SecurityContext,
    results: Dict[str, Any],
    executed: List[Dict[str, Any]],
) -> str:
    """Produces verified, evidence-grounded Markdown responses tailored strictly to user intent."""
    role = context.user_role
    company = context.company_name
    intent = _detect_user_intent(message)

    # -------------------------------------------------------------------------
    # INTENT 1: ACTION REQUEST (Task scheduled, updated, completed, or deleted)
    # -------------------------------------------------------------------------
    mutation_tools = [
        "update_checklist_status", "update_task_status", "update_checklist",
        "update_room", "create_room", "create_checklist",
        "create_clinical_task", "delete_clinical_checklist",
    ]
    if intent == "action" or any(t in results for t in mutation_tools):
        action_parts = []
        if "create_clinical_task" in results:
            ct = results["create_clinical_task"]
            staff_disp = ct.get('assigned_staff_id') or "Unassigned"
            if "search_staff" in results:
                for s in results["search_staff"].get("staff", []):
                    if s.get("staff_id") == ct.get("assigned_staff_id"):
                        staff_disp = f"{s.get('name')} ({s.get('role')})"
                        break
            action_parts.append(
                f"### ✅ Clinical Task Scheduled\n"
                f"- **Title:** **{ct.get('title')}**\n"
                f"- **Priority:** `{ct.get('priority')}`\n"
                f"- **Task ID:** `{ct.get('task_id')}`\n"
                f"- **Assigned Provider:** {staff_disp}\n"
                f"- **Room:** `{ct.get('room_id')}`\n"
                f"- **Due Date:** `{ct.get('due_date')}`\n\n"
                f"Task recorded in clinic database under `{role}` authorization."
            )
        if "update_task_status" in results:
            uts = results["update_task_status"]
            action_parts.append(
                f"### ✅ Task Updated\n"
                f"- **Task ID:** `{uts.get('task_id')}`\n"
                f"- **Title:** **{uts.get('title')}**\n"
                f"- **Status:** `{uts.get('updated_status')}`\n"
                f"- **Assigned Provider:** `{uts.get('assigned_to')}`\n"
                f"- **Priority:** `{uts.get('priority')}`\n\n"
                f"State change successfully committed to the database."
            )
        if "update_checklist_status" in results:
            ucs = results["update_checklist_status"]
            action_parts.append(
                f"### 📋 Checklist Status Updated\n"
                f"- **Checklist ID:** `{ucs.get('checklist_id')}`\n"
                f"- **Title:** {ucs.get('title')}\n"
                f"- **Status:** `{'Completed' if ucs.get('is_completed') else 'Pending'}`\n"
            )
        if "update_checklist" in results:
            uc = results["update_checklist"]
            action_parts.append(
                f"### 📋 Checklist Assigned & Updated\n"
                f"- **Checklist ID:** `{uc.get('checklist_id')}`\n"
                f"- **Title:** **{uc.get('title')}**\n"
                f"- **Assigned Staff:** **{uc.get('assigned_staff_name', 'Unassigned')}** (`{uc.get('assigned_staff_id')}`)\n"
                f"- **Category:** `{uc.get('category')}`\n"
                f"- **Status:** `{'Completed' if uc.get('is_completed') else 'Pending'}`\n\n"
                f"Checklist assignment successfully committed to PostgreSQL under `{role}` authorization."
            )
        if "update_room" in results:
            ur = results["update_room"]
            action_parts.append(
                f"### 🚪 Room Status Updated\n"
                f"- **Room ID:** `{ur.get('room_id')}`\n"
                f"- **Room:** **Room {ur.get('room_number')} — {ur.get('name')}**\n"
                f"- **Type:** `{ur.get('room_type')}`\n"
                f"- **Status:** `{ur.get('room_status')}`\n\n"
                f"Room status change successfully committed to PostgreSQL under `{role}` authorization."
            )
        if "create_room" in results:
            cr = results["create_room"]
            action_parts.append(
                f"### 🚪 Room Created\n"
                f"- **Room ID:** `{cr.get('room_id')}`\n"
                f"- **Room:** **Room {cr.get('room_number')} — {cr.get('name')}**\n"
                f"- **Type:** `{cr.get('room_type')}`\n"
                f"- **Status:** `{cr.get('status')}`\n\n"
                f"Room record successfully committed to PostgreSQL under `{role}` authorization."
            )
        if "create_checklist" in results:
            cc = results["create_checklist"]
            action_parts.append(
                f"### 📋 Checklist Created\n"
                f"- **Checklist ID:** `{cc.get('checklist_id')}`\n"
                f"- **Title:** **{cc.get('title')}**\n"
                f"- **Category:** `{cc.get('category')}`\n"
                f"- **Assigned Staff ID:** `{cc.get('assigned_staff_id')}`\n\n"
                f"Checklist record successfully committed to PostgreSQL under `{role}` authorization."
            )
        if "delete_clinical_checklist" in results:
            dcc = results["delete_clinical_checklist"]
            action_parts.append(
                f"### 🗑️ Checklist Record Permanently Deleted\n"
                f"- **Checklist ID:** `{dcc.get('checklist_id')}`\n"
                f"- **Title:** {dcc.get('title')}\n"
            )
        if action_parts:
            return "\n\n".join(action_parts)

    # -------------------------------------------------------------------------
    # INTENT 2: EXPLANATION REQUEST (Explain why task is pending / task details)
    # -------------------------------------------------------------------------
    if intent == "explanation":
        if "list_tasks" in results:
            lt = results["list_tasks"]
            t_list = lt.get("tasks", [])
            target_id = _extract_task_id(message)
            matched_task = next((t for t in t_list if target_id in t.get("task_id", "").lower()), None)
            if not matched_task and t_list:
                matched_task = t_list[0]

            if matched_task:
                desc = matched_task.get("description") or "Standard clinical protocol in progress."
                due = matched_task.get("due_date", "N/A")
                is_over = matched_task.get("is_overdue", False)
                status_str = matched_task.get("status", "Pending")

                explanation_text = (
                    f"According to clinic database records, this task is currently **{status_str}**.\n\n"
                    f"**Documented Clinical Reason / Notes:**\n"
                    f"> *\"{desc}\"*\n\n"
                    f"- **Assigned Provider:** {matched_task.get('assigned_to')}\n"
                    f"- **Location:** {matched_task.get('room_name')}\n"
                    f"- **Deadline:** `{due}` {'(⚠️ Overdue)' if is_over else ''}\n\n"
                    f"*(Note: Grounded strictly in authorized PostgreSQL clinic records. No hypothetical reasons invented.)*"
                )
                return (
                    f"### 📋 Task Investigation: **{matched_task.get('title')}** (`{matched_task.get('task_id')}`)\n\n"
                    + explanation_text
                )
            else:
                return (
                    f"### 🔍 Task Not Found\n\n"
                    f"No task matching ID `{target_id}` was found in tenant partition `{context.tenant_id}`."
                )

    # -------------------------------------------------------------------------
    # INTENT 3: RETRIEVAL REQUEST (List tasks, inventory items, staff, rooms)
    # -------------------------------------------------------------------------
    if intent == "retrieval":
        retrieval_parts = []
        if "list_tasks" in results:
            lt = results["list_tasks"]
            t_list = lt.get("tasks", [])
            tot = lt.get("total_returned", len(t_list))
            pend = lt.get("pending_count", 0)
            over = lt.get("overdue_count", 0)
            if not t_list:
                retrieval_parts.append("### 📋 Clinical Tasks\n\n*No clinical tasks matched the specified filter criteria.*")
            else:
                t_rows = "\n".join([
                    f"- **[{t.get('priority', 'Normal')}]** `{t.get('task_id')}`: **{t.get('title')}** — Status: `{t.get('status')}` • Room: {t.get('room_name')} • Assignee: {t.get('assigned_to')} (*Due: {t.get('due_date')}*{' ⚠️ OVERDUE' if t.get('is_overdue') else ''})"
                    for t in t_list[:15]
                ])
                retrieval_parts.append(
                    f"### 📋 Clinical Tasks ({tot} items — {pend} Pending, {over} Overdue)\n\n"
                    f"{t_rows}"
                )
                if any(w in message.lower() for w in ["priority", "priorities", "suggest"]):
                    retrieval_parts.append(
                        "#### 🎯 Recommended Priority Actions:\n"
                        "1. **Critical Clinical Care:** Prioritize statutory narcotics audits and emergency crash cart refills.\n"
                        "2. **Room Readiness:** Execute room turnover and disinfection ahead of scheduled intake times.\n"
                        "3. **Overdue Lab Reviews:** Expedite physician sign-offs for pending laboratory results."
                    )

        if "get_inventory_status" in results:
            inv = results["get_inventory_status"]
            alerts = inv.get("alerts", [])
            items = inv.get("items", [])
            alerts_md = "\n".join([f"- ⚠️ {a}" for a in alerts]) if alerts else "- No alerts for the returned items."
            if items:
                item_rows = [
                    f"| {it.get('name')} | {it.get('current_stock')} {it.get('unit')} | Min: {it.get('min_threshold')} | "
                    f"{it.get('stock_status')} | {it.get('expiry_date') or '—'} | {it.get('expiry_state')} | {it.get('location')} |"
                    for it in items[:10]
                ]
                items_table = (
                    "| Supply Item | Quantity | Threshold | Stock Status | Expiry | Expiry Status | Location |\n"
                    "| :--- | :---: | :---: | :---: | :--- | :---: | :--- |\n" + "\n".join(item_rows)
                )
            else:
                items_table = f"*{inv.get('message') or 'No inventory items returned.'}*"
            retrieval_parts.append(
                f"### 📦 Medical Supplies & Inventory Status\n\n"
                f"- **Low Stock:** **{inv.get('low_stock_count', 0)}** items • **Out of Stock:** **{inv.get('out_of_stock_count', 0)}** items\n\n"
                f"{items_table}\n\n"
                f"#### Active Alerts:\n{alerts_md}"
            )

        if "search_staff" in results:
            stf = results["search_staff"]
            staff_items = stf.get("staff", [])
            if not staff_items:
                retrieval_parts.append(f"### 👨‍⚕️ Staff Search\n\nNo staff members matching `{stf.get('query')}` found.")
            else:
                stf_rows = "\n".join([f"- **{s.get('name')}** ({s.get('role')}) — ID: `{s.get('staff_id')}` • Status: **{s.get('status_label')}**" for s in staff_items])
                retrieval_parts.append(f"### 👨‍⚕️ Clinical Staff Directory\n\n{stf_rows}")

        if "search_rooms" in results:
            sr = results["search_rooms"]
            rooms = sr.get("rooms", [])
            if rooms:
                r_rows = "\n".join([f"- **{r.get('display_label')}** (Type: `{r.get('room_type')}`, Status: `{r.get('status')}`)" for r in rooms])
                retrieval_parts.append(f"### 🏥 Room Directory\n\n{r_rows}")

        if "get_room_turnover_status" in results and "get_team_task_performance" not in results:
            retrieval_parts.append(_format_rooms_block(results["get_room_turnover_status"]))

        if "get_practice_summary" in results:
            ps = results["get_practice_summary"]
            retrieval_parts.append(
                f"### 🏥 Practice Facility Overview — **{ps.get('facility_name', company)}**\n\n"
                f"- **Tenant Partition:** `{ps.get('tenant_id', context.tenant_id)}`\n"
                f"- **Monitored Rooms:** `{ps.get('total_rooms', 0)}` rooms\n"
                f"- **Clinical Staff On Roster:** `{ps.get('staff_count', 0)}` providers\n"
                f"- **Active Tasks:** `{ps.get('active_tasks_count', 0)}` ({ps.get('completion_rate', 0.0)}% complete)\n"
                f"- **Low Stock Supply Alerts:** `{ps.get('inventory_alerts_count', 0)}` items"
            )

        if "get_checklist_details" in results:
            cd = results["get_checklist_details"]
            retrieval_parts.append(
                f"### 📋 Checklist Details: **{cd.get('title')}** (`{cd.get('checklist_id')}`)\n\n"
                f"- **Category:** `{cd.get('category')}`\n"
                f"- **Status:** `{'Completed' if cd.get('is_completed') else 'Pending'}`\n"
                f"- **Frequency:** `{cd.get('frequency')}`\n"
                f"- **Assigned Provider:** {cd.get('assigned_staff_name')} (`{cd.get('assigned_staff_id')}`)\n"
                f"- **Tenant Partition:** `{cd.get('tenant_id')}`"
            )

        if "list_checklists" in results:
            lc = results["list_checklists"]
            chks = lc.get("checklists", [])
            if chks:
                chk_rows = "\n".join([f"- **[{'Completed' if c.get('is_completed') else 'Pending'}]** `{c.get('checklist_id')}`: **{c.get('title')}** (Assignee: {c.get('assigned_staff_id') or 'Unassigned'})" for c in chks[:15]])
                retrieval_parts.append(f"### 📋 Clinical Checklists ({lc.get('total_returned', len(chks))} items)\n\n{chk_rows}")
            else:
                retrieval_parts.append("### 📋 Clinical Checklists\n\n*No checklists found matching criteria.*")

        if "get_room_details" in results:
            rd = results["get_room_details"]
            retrieval_parts.append(
                f"### 🚪 Room Details: **{rd.get('name')}** (`{rd.get('room_id')}`)\n\n"
                f"- **Room Number:** `{rd.get('room_number')}`\n"
                f"- **Room Type:** `{rd.get('room_type')}`\n"
                f"- **Live Status:** `{rd.get('status')}`\n"
                f"- **Tenant Partition:** `{rd.get('tenant_id')}`"
            )

        if "get_task_details" in results:
            td = results["get_task_details"]
            retrieval_parts.append(
                f"### 📋 Task Details: **{td.get('title', 'Clinical Task')}** (`{td.get('task_id')}`)\n\n"
                f"- **Priority:** `{td.get('priority')}`\n"
                f"- **Status:** `{td.get('status_value')}`\n"
                f"- **Due Date:** `{td.get('due_date')}`\n"
                f"- **Room:** {td.get('room_name') or td.get('room_id')}\n"
                f"- **Assigned Provider:** {td.get('assigned_staff_name') or td.get('assigned_staff_id')}\n"
                f"- **Clinical Notes:** {td.get('description', 'N/A')}"
            )

        if "get_operational_task_conflicts" in results:
            oc = results["get_operational_task_conflicts"]
            items = oc.get("items", [])
            tot = oc.get("total_conflicts", len(items))
            hol = oc.get("holiday_conflicts", 0)
            dnd = oc.get("dnd_conflicts", 0)
            inact = oc.get("inactive_login_conflicts", 0)
            over = oc.get("overdue_count", 0)
            unassign = oc.get("unassigned_count", 0)

            conflict_rows = []
            for it in items[:15]:
                conflict_rows.append(f"- ⚠️ **[{it.get('conflict_type')}]** `{it.get('item_id')}`: {it.get('message')} — *{it.get('recommendation')}*")
            conflicts_md = "\n".join(conflict_rows) if conflict_rows else "- ✅ *No operational task conflicts or leave conflicts detected.*"

            retrieval_parts.append(
                f"### ⚠️ Operational Bottlenecks & Availability Conflicts ({tot} Total)\n\n"
                f"- **Holiday Conflicts:** {hol} • **Do Not Disturb (DND):** {dnd} • **Inactive Login Staff:** {inact}\n"
                f"- **Overdue Tasks:** {over} • **Unassigned Queue:** {unassign}\n\n"
                f"{conflicts_md}"
            )

        if "get_staff_availability_and_leaves" in results:
            sa = results["get_staff_availability_and_leaves"]
            staff_list = sa.get("staff", [])
            stf_rows = []
            for s in staff_list[:15]:
                stf_rows.append(
                    f"- **{s.get('name')}** ({s.get('role')}) — Status: **{s.get('work_status')}** (On Shift: {s.get('on_shift')}) • "
                    f"Last Login: `{s.get('last_login_at') or 'Never'}` • Available: **{'Yes' if s.get('is_available_for_tasks') else 'No'}**"
                )
            retrieval_parts.append(
                f"### 👨‍⚕️ Staff Availability & Leave Calendar ({sa.get('total_count', len(staff_list))} staff)\n\n"
                + ("\n".join(stf_rows) if stf_rows else "*No staff records found.*")
            )

        if retrieval_parts:
            return "\n\n".join(retrieval_parts)

    # -------------------------------------------------------------------------
    # INTENT 4: CONCISE ANALYSIS ("How is my team performing?")
    # -------------------------------------------------------------------------
    if intent == "concise_analysis":
        sections = []
        if "get_team_task_performance" in results:
            sections.append(_format_performance_block(results["get_team_task_performance"], role))
        if "get_room_turnover_status" in results:
            sections.append(_format_rooms_block(results["get_room_turnover_status"]))
        if sections:
            return "\n\n".join(sections)

    # -------------------------------------------------------------------------
    # INTENT 5: DETAILED ANALYSIS ("Analyse my team's performance over the last month")
    # -------------------------------------------------------------------------
    if intent == "detailed_analysis":
        sections = []
        sections.append(f"### 📊 Clinical Operations & Team Performance Analysis — {company}")
        sections.append(f"**Audit & Security Scope:** `{role}` • Tenant: `{context.tenant_id}`")
        if "get_team_task_performance" in results:
            perf = results["get_team_task_performance"]
            sections.append(_format_performance_block(perf, role))
        if "get_room_turnover_status" in results:
            sections.append(_format_rooms_block(results["get_room_turnover_status"]))
        return "\n\n".join(sections)

    # -------------------------------------------------------------------------
    # INTENT 6: FORMAL REPORT ("Generate a monthly team performance report")
    # -------------------------------------------------------------------------
    sections = []
    sections.append(f"## 🏥 PractiCare Operations Intelligence — {company}")
    sections.append(f"**Security Context:** `{role}` • Tenant: `{context.tenant_id}` • Verified DB Sync")

    if "get_team_task_performance" in results:
        sections.append(_format_performance_block(results["get_team_task_performance"], role))
    if "get_room_turnover_status" in results:
        sections.append(_format_rooms_block(results["get_room_turnover_status"]))
    if "search_rooms" in results and "create_clinical_task" not in results:
        sr = results["search_rooms"]
        rooms = sr.get("rooms", [])
        if rooms:
            sections.append(f"### 🏥 Room Resolution\n\n" + "\n".join([f"- **{r.get('display_label')}**" for r in rooms]))
    if "create_clinical_task" in results:
        ct = results["create_clinical_task"]
        sections.append(f"### ✅ Clinical Task Scheduled\n- **Title:** {ct.get('title')}\n- **Task ID:** `{ct.get('task_id')}`\n- **Room:** `{ct.get('room_id')}`")
    if "update_task_status" in results:
        uts = results["update_task_status"]
        sections.append(f"### ✅ Task Status Updated\n- **Task ID:** `{uts.get('task_id')}`\n- **Status:** `{uts.get('updated_status')}`")
    if "list_tasks" in results:
        lt = results["list_tasks"]
        t_list = lt.get("tasks", [])
        if t_list:
            t_rows = "\n".join([f"- **[{t.get('priority')}]** `{t.get('task_id')}`: {t.get('title')} ({t.get('status')})" for t in t_list[:5]])
            sections.append(f"### 📋 Tasks Overview\n\n{t_rows}")
    if "get_inventory_status" in results:
        inv = results["get_inventory_status"]
        sections.append(f"### 📦 Inventory Status\n- **Low Stock:** {inv.get('low_stock_count', 0)} items\n- **Out of Stock:** {inv.get('out_of_stock_count', 0)} items")

    sections.append(_format_recommendations_block(results, role))
    return "\n\n".join(sections)


def _format_performance_block(perf: Dict[str, Any], role: str) -> str:
    if role == "CLINICAL_AUDITOR":
        audit = perf.get("audit_metrics", {})
        return (
            f"### 📊 Clinical Compliance & Quality Audit (Anonymized Aggregate)\n\n"
            f"- **Audit Scope:** Complete Tenant Clinic Operations (Zero Employee PII)\n"
            f"- **Total Monitored Tasks:** `{audit.get('total_audited_tasks', 0)}`\n"
            f"- **Pass / Completion Ratio:** **{audit.get('pass_ratio', 0.0)}%**\n"
            f"- **Compliance Status:** **{audit.get('compliance_score', 'Compliant')}**\n"
            f"- **Overdue Ratio:** `{audit.get('overdue_ratio', 0.0)}%` ({audit.get('overdue_count', 0)} items)\n\n"
            f"*PII Redaction: Employee names, provider IDs, and compensation metrics are strictly redacted under Clinical Auditor scoping rules.*"
        )

    if role == "NURSE_STAFF":
        metrics = perf.get("metrics", {})
        tasks = perf.get("operational_tasks", [])
        tasks_md = "\n".join([f"- **[{t.get('priority', 'Normal')}]** {t.get('title')} — Room: {t.get('room_name')} (*Due: {t.get('due_date')}*)" for t in tasks[:5]]) if tasks else "- *No urgent operational tasks pending.*"
        return (
            f"### 🩺 Nurse Operational Floor & Hygiene Report\n\n"
            f"- **Active Floor Duties:** `{metrics.get('operational_tasks_count', 0)}`\n"
            f"- **Overall Completion Rate:** **{metrics.get('overall_completion_rate', 100.0)}%**\n"
            f"- **Critical Tasks Pending:** `{metrics.get('overdue_tasks_count', 0)}`\n\n"
            f"#### Assigned Duties & Floor Pool:\n{tasks_md}\n\n"
            f"*Executive Protection: Physician evaluations, doctor billing metrics, and administrative compensation logs are securely redacted.*"
        )

    if role == "ATTENDING_PHYSICIAN":
        metrics = perf.get("metrics", {})
        dept_tasks = perf.get("department_tasks", [])
        tasks_md = "\n".join([f"- **[{t.get('priority', 'Normal')}]** {t.get('title')} (Status: `{t.get('status')}`) — Assigned: {t.get('assigned_to')}" for t in dept_tasks[:5]]) if dept_tasks else "- *No department tasks pending.*"
        return (
            f"### 🩺 Clinical Department Briefing & Procedure Workload\n\n"
            f"- **Department Task Volume:** `{metrics.get('total_department_tasks', 0)}`\n"
            f"- **Clinical Completion Rate:** **{metrics.get('completion_rate', 0.0)}%**\n"
            f"- **Overdue Bottlenecks:** `{metrics.get('overdue_tasks_count', 0)}`\n\n"
            f"#### Department Procedures & Room Tasks:\n{tasks_md}\n\n"
            f"*Scoped strictly to clinical department rooms. Executive administrative overhead is redacted.*"
        )

    # CLINIC_OWNER / Default
    metrics = perf.get("metrics", {})
    workloads = perf.get("provider_workloads", [])
    if workloads:
        wl_rows = [f"| {w.get('name')} | {w.get('role')} | {w.get('assigned_tasks_count')} | {w.get('completed_tasks_count')} | {w.get('completion_rate')}% | {w.get('active_status')} |" for w in workloads]
        wl_md = (
            "| Staff Member | Role | Assigned | Completed | Rate | Shift Status |\n"
            "| :--- | :--- | :---: | :---: | :---: | :--- |\n" + "\n".join(wl_rows)
        )
    else:
        wl_md = "*No provider workload records available.*"

    bottlenecks = perf.get("bottlenecks", [])
    bn_md = "\n".join([f"- ⚠️ **{b.get('title')}** (Priority: `{b.get('priority')}`, Assigned: {b.get('assigned_staff')}, Room: {b.get('room')})" for b in bottlenecks[:4]]) if bottlenecks else "✅ No critical bottlenecks detected."

    return (
        f"### 📈 Comprehensive Clinic Executive Performance & Team Performance Summary\n\n"
        f"- **Overall Completion Rate:** **{metrics.get('completion_rate', 0.0)}%** ({metrics.get('completed_tasks_count', 0)}/{metrics.get('total_tasks_count', 0)} tasks)\n"
        f"- **Pending Operational Tasks:** `{metrics.get('pending_tasks_count', 0)}`\n"
        f"- **Overdue Bottlenecks:** `{metrics.get('overdue_tasks_count', 0)}`\n"
        f"- **Unassigned Task Queue:** `{metrics.get('unassigned_tasks_count', 0)}` items\n\n"
        f"#### Provider Workload Breakdown:\n\n{wl_md}\n\n"
        f"#### Operational Bottlenecks:\n{bn_md}"
    )


def _format_rooms_block(rm: Dict[str, Any]) -> str:
    breakdown = rm.get("status_breakdown", {})
    total = rm.get("total_rooms", 0)
    needs_to = rm.get("needs_turnover_count", 0)
    bd_str = ", ".join([f"**{k}:** {v}" for k, v in breakdown.items()])
    return (
        f"### 🚪 Real-Time Room & Turnover Status\n\n"
        f"- **Total Rooms Monitored:** `{total}`\n"
        f"- **Current Distribution:** {bd_str}\n"
        f"- **Turnover / Sanitization Required:** **{needs_to} rooms**\n\n"
        f"{'⚠️ Immediate sanitization recommended for rooms in Turnover state.' if needs_to > 0 else '✅ All rooms operational.'}"
    )


def _format_recommendations_block(results: Dict[str, Any], role: str) -> str:
    recs = []
    if "get_team_task_performance" in results:
        perf = results["get_team_task_performance"]
        metrics = perf.get("metrics") or perf.get("audit_metrics") or {}
        overdue = metrics.get("overdue_tasks_count") or metrics.get("overdue_count") or 0
        if overdue > 0:
            recs.append(f"Prioritize re-assigning the **{overdue} overdue clinical tasks** to active floor staff.")
        unassigned = metrics.get("unassigned_tasks_count", 0)
        if unassigned > 0:
            recs.append(f"Allocate **{unassigned} unassigned duties** in the triage queue to prevent procedure delays.")

    if "get_room_turnover_status" in results:
        rm = results["get_room_turnover_status"]
        if rm.get("needs_turnover_count", 0) > 0:
            recs.append(f"Dispatch nursing team for autoclave sterilization and room turnover in Exam suites.")

    if not recs:
        recs.append("All clinical workflows and room schedules are operating within standard parameters.")

    rec_items = "\n".join([f"- {r}" for r in recs])
    return f"#### 💡 Recommended Clinical Follow-up Actions:\n{rec_items}"


# ==============================================================================
# COMPILED LANGGRAPH ORCHESTRATOR CLASS
# ==============================================================================

class PractiCareLangGraphAgent:
    """
    Formal LangGraph StateGraph engine for PractiCare Clinical Operations.
    """

    def __init__(self):
        if LANGGRAPH_AVAILABLE and MemorySaver is not None and StateGraph is not None:
            self.checkpointer = MemorySaver()
            self.workflow = self._build_graph()
        else:
            self.checkpointer = None
            self.workflow = None

    def _build_graph(self):

        graph = StateGraph(AgentState)

        # Add Nodes
        graph.add_node("agent_reasoning", agent_reasoning_node)
        graph.add_node("tool_execution", tool_execution_node)
        graph.add_node("result_analysis", result_analysis_node)
        graph.add_node("report_synthesis", report_synthesis_node)

        # Edges
        graph.add_edge(START, "agent_reasoning")

        # Conditional edge: Reasoning -> Tool Execution OR Report Synthesis
        def route_after_reasoning(state: AgentState):
            if state.get("status") in ("failed", "blocked"):
                return "report_synthesis"
            if state.get("approval_pending"):
                return "report_synthesis"
            if not state.get("tool_calls_planned"):
                return "report_synthesis"
            return "tool_execution"

        graph.add_conditional_edges("agent_reasoning", route_after_reasoning, {
            "report_synthesis": "report_synthesis",
            "tool_execution": "tool_execution",
        })

        graph.add_edge("tool_execution", "result_analysis")

        # Conditional edge: Result Analysis -> More Tools OR Report Synthesis
        def route_after_analysis(state: AgentState):
            if state.get("approval_pending"):
                return "report_synthesis"
            if state.get("more_tools_needed") and state.get("current_iteration", 0) < MAX_ITERATIONS:
                return "agent_reasoning"
            return "report_synthesis"

        graph.add_conditional_edges("result_analysis", route_after_analysis, {
            "agent_reasoning": "agent_reasoning",
            "report_synthesis": "report_synthesis",
        })

        graph.add_edge("report_synthesis", END)

        return graph.compile(checkpointer=self.checkpointer)

    def run(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        context: SecurityContext,
        db: Session,
        approval_id: Optional[str] = None,
        agent_mode: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the LangGraph StateGraph pipeline.
        Returns:
            {
                "reply": "Markdown report...",
                "tool_calls_executed": [{"tool": "...", "status": "SUCCESS"}],
                "status": "completed" | "approval_required" | "blocked" | "failed",
                "approval_pending": {...} (if human approval required),
                "metrics": {
                    "total_latency_ms": ...,
                    "gemini_latency_ms": ...,
                    "agent_mode": ...,
                    "model_name": ...,
                    "input_tokens": ...,
                    "output_tokens": ...,
                    "total_tokens": ...,
                    "estimated_cost_usd": ...,
                    "tool_call_count": ...,
                    "iterations": ...
                }
            }
        """
        start_time = time.perf_counter()

        resolved_mode = (agent_mode or os.getenv("AI_AGENT_MODE", "gemini")).lower()
        model_name = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

        initial_state: AgentState = {
            "conversation_id": conversation_id,
            "message": message,
            "conversation_history": conversation_history or [],
            "tenant_id": context.tenant_id,
            "user_id": context.user_id,
            "user_role": context.user_role,
            "company_name": context.company_name,
            "approval_id": approval_id,
            "current_iteration": 0,
            "tool_calls_planned": [],
            "executed_tools": [],
            "tool_results": {},
            "approval_pending": None,
            "more_tools_needed": True,
            "final_reply": None,
            "status": "in_progress",
            "metrics": {},
            "agent_mode": resolved_mode,
            "model_name": model_name,
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_latency_ms": 0.0,
            "langchain_messages": [],
        }

        # Thread isolation: tenant_id + user_id + conversation_id ensures strict boundary
        thread_id = f"th_{context.tenant_id}_{context.user_id}_{conversation_id or 'adhoc'}"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "db": db,
                "context": context,
            }
        }

        # Run through LangGraph if available, otherwise direct sequential pipeline
        if not self.workflow:
            # Nodes return partial updates; merge them like LangGraph's default reducer does.
            def step(node, current):
                return {**current, **(node(current, config) or {})}

            state = dict(initial_state)
            for _ in range(MAX_ITERATIONS):
                state = step(agent_reasoning_node, state)
                if state.get("status") in ("failed", "blocked") or state.get("approval_pending") or not state.get("tool_calls_planned"):
                    break
                state = step(tool_execution_node, state)
                state = step(result_analysis_node, state)
                if state.get("approval_pending") or not state.get("more_tools_needed"):
                    break
            final_state = step(report_synthesis_node, state)
        else:
            final_state = self.workflow.invoke(initial_state, config=config)


        total_latency = round((time.perf_counter() - start_time) * 1000, 2)

        executed_tools = [
            {
                "tool": t["tool"],
                "status": t["status"],
                "duration_ms": t.get("duration_ms") or t.get("result", {}).get("duration_ms"),
                "correlation_id": t.get("correlation_id") or t.get("result", {}).get("correlation_id"),
                "resource_id": t.get("resource_id") or t.get("result", {}).get("resource_id") or t.get("result", {}).get("task_id"),
            }
            for t in final_state.get("executed_tools", [])
        ]

        inp_tok = final_state.get("input_tokens", 0)
        out_tok = final_state.get("output_tokens", 0)
        tot_tok = inp_tok + out_tok

        # Estimated cost in USD based on Flash pricing
        cost_usd = round(
            (inp_tok * (INPUT_TOKEN_PRICE_PER_MILLION / 1_000_000))
            + (out_tok * (OUTPUT_TOKEN_PRICE_PER_MILLION / 1_000_000)),
            6
        )

        metrics = {
            "total_latency_ms": total_latency,
            "gemini_latency_ms": final_state.get("llm_latency_ms", 0.0),
            "agent_mode": final_state.get("agent_mode", agent_mode),
            "model_name": final_state.get("model_name", model_name),
            "model_calls": final_state.get("model_calls", 0),
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
            "total_tokens": tot_tok,
            "estimated_cost_usd": cost_usd,
            "tool_call_count": len(executed_tools),
            "iterations": final_state.get("current_iteration", 1),
        }

        # Add any internal error or detail if present
        if final_state.get("metrics"):
            metrics.update(final_state["metrics"])

        return {
            "reply": final_state.get("final_reply", "Operations report generated."),
            "tool_calls_executed": executed_tools,
            "status": final_state.get("status", "completed"),
            "approval_pending": final_state.get("approval_pending"),
            "metrics": metrics,
        }


agent = PractiCareLangGraphAgent()
