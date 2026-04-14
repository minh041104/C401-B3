"""
graph.py - Supervisor Orchestrator

Architecture:
    Input -> Supervisor -> [retrieval_worker | policy_tool_worker | human_review] -> synthesis -> Output

Run:
    python graph.py
"""

import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import Literal, Optional, TypedDict

from workers.policy_tool import run as policy_tool_run
from workers.retrieval import run as retrieval_run
from workers.synthesis import run as synthesis_run


class AgentState(TypedDict):
    # Input
    task: str

    # Supervisor decisions
    route_reason: str
    risk_high: bool
    needs_tool: bool
    hitl_triggered: bool

    # Worker outputs
    retrieved_chunks: list
    retrieved_sources: list
    policy_result: dict
    mcp_tools_used: list

    # Final output
    final_answer: str
    sources: list
    confidence: float

    # Trace and history
    history: list
    workers_called: list
    worker_io_logs: list
    supervisor_route: str
    latency_ms: Optional[int]
    run_id: str


def make_initial_state(task: str) -> AgentState:
    """Initialize state for a new run."""
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "worker_io_logs": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }


ALLOWED_ROUTES = {"retrieval_worker", "policy_tool_worker", "human_review"}

ACCESS_POLICY_KEYWORDS = [
    "cap quyen",
    "phe duyet",
    "approval",
    "access",
    "admin access",
    "level 2",
    "level 3",
    "level 4",
    "contractor",
    "it security",
    "tech lead",
    "tam thoi",
]

REFUND_BASE_KEYWORDS = [
    "hoan tien",
    "refund",
    "store credit",
]

REFUND_DECISION_KEYWORDS = [
    "flash sale",
    "license",
    "license key",
    "subscription",
    "ky thuat so",
    "kich hoat",
    "dang ky",
    "ngoai le",
    "duoc khong",
    "ap dung",
    "policy nao",
    "store credit",
    "gia tri",
    "tien goc",
    "31/01",
    "30/01",
    "01/02",
    "truoc 01/02",
    "v3",
    "v4",
]

RETRIEVAL_KB_KEYWORDS = [
    "sla",
    "ticket",
    "p1",
    "p2",
    "p3",
    "p4",
    "escalation",
    "incident",
    "thong bao",
    "notify",
    "pagerduty",
    "slack",
    "faq",
    "mat khau",
    "vpn",
    "remote",
    "probation",
    "onboarding",
    "nghi phep",
    "hr",
    "helpdesk",
]

RISK_KEYWORDS = [
    "khan cap",
    "emergency",
    "critical",
    "2am",
    "2 am",
    "ngoai gio",
    "incident",
    "p1",
    "admin access",
]

MANUAL_REVIEW_KEYWORDS = [
    "khong ro",
    "unknown",
    "manual review",
    "nguoi kiem tra",
    "xac minh tay",
]

TEMPORAL_POLICY_KEYWORDS = ["31/01", "30/01", "01/02", "truoc 01/02", "v3", "v4"]


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents).strip()


def _find_matches(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _clone_value(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def _console_text(value) -> str:
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _record_worker_failure(
    state: AgentState,
    worker_name: str,
    error_code: str,
    error: Exception,
    fallback_updates: dict,
) -> AgentState:
    state.setdefault("history", [])
    state.setdefault("workers_called", [])
    state.setdefault("worker_io_logs", [])

    if not state["workers_called"] or state["workers_called"][-1] != worker_name:
        state["workers_called"].append(worker_name)

    safe_updates = {
        key: _clone_value(value) for key, value in fallback_updates.items()
    }
    for key, value in safe_updates.items():
        state[key] = value

    reason = str(error)
    state["history"].append(f"[{worker_name}] wrapper ERROR: {reason}")
    state["worker_io_logs"].append(
        {
            "worker": worker_name,
            "input": {"task": state.get("task", "")},
            "output": safe_updates,
            "error": {"code": error_code, "reason": reason},
        }
    )
    return state


# -----------------------------------------------------------------------------
# 1. Supervisor node
# -----------------------------------------------------------------------------

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor reads the task and decides:
    1. Which worker should receive the task first
    2. Whether MCP/tool access is needed
    3. Whether the task is high-risk and may require HITL later
    """
    task = _normalize_text(state["task"])
    state["history"].append(f"[supervisor] received task: {state['task'][:80]}")

    access_matches = _find_matches(task, ACCESS_POLICY_KEYWORDS)
    refund_base_matches = _find_matches(task, REFUND_BASE_KEYWORDS)
    refund_decision_matches = _find_matches(task, REFUND_DECISION_KEYWORDS)
    retrieval_matches = _find_matches(task, RETRIEVAL_KB_KEYWORDS)
    risk_matches = _find_matches(task, RISK_KEYWORDS)
    manual_review_matches = _find_matches(task, MANUAL_REVIEW_KEYWORDS)
    has_error_code = bool(re.search(r"\berr[- ]?[a-z0-9-]+\b", task))

    cross_domain = bool(
        (access_matches or refund_decision_matches) and retrieval_matches
    )
    temporal_policy = bool(
        refund_base_matches
        and any(marker in task for marker in TEMPORAL_POLICY_KEYWORDS)
    )

    route = "retrieval_worker"
    needs_tool = False
    risk_high = bool(risk_matches or has_error_code or cross_domain or temporal_policy)
    reason_parts: list[str] = []

    if access_matches:
        route = "policy_tool_worker"
        needs_tool = True
        reason_parts.append(f"access-control routing via {access_matches}")
        if retrieval_matches:
            reason_parts.append(
                f"policy route overrides retrieval signals {retrieval_matches}"
            )
    elif refund_base_matches and (refund_decision_matches or temporal_policy or "duoc khong" in task):
        route = "policy_tool_worker"
        needs_tool = True
        refund_signals = _unique(refund_base_matches + refund_decision_matches)
        reason_parts.append(
            f"refund decision/exception routing via {refund_signals}"
        )
    elif has_error_code and manual_review_matches:
        route = "human_review"
        reason_parts.append(
            f"error code plus manual-review signal {manual_review_matches}"
        )
    elif retrieval_matches:
        route = "retrieval_worker"
        reason_parts.append(f"knowledge-base retrieval via {retrieval_matches}")
    elif refund_base_matches:
        route = "retrieval_worker"
        reason_parts.append(
            f"simple refund fact lookup via {refund_base_matches}"
        )
    else:
        reason_parts.append("fallback to retrieval_worker for generic KB lookup")

    if has_error_code and route != "human_review":
        reason_parts.append(
            "error code detected -> retrieve evidence first, escalate to HITL only if evidence remains weak"
        )

    if temporal_policy:
        reason_parts.append("temporal policy signal detected")

    if cross_domain:
        reason_parts.append("cross-domain query detected")

    if risk_high:
        reason_parts.append(
            f"risk_high=True from {risk_matches or ['error_code_or_cross_domain']}"
        )

    route_reason = " | ".join(reason_parts) or "fallback to retrieval_worker"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(f"[supervisor] route={route} reason={route_reason}")

    return state


# -----------------------------------------------------------------------------
# 2. Route decision
# -----------------------------------------------------------------------------

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """Return the next worker based on supervisor_route in state."""
    route = state.get("supervisor_route", "retrieval_worker")
    if route not in ALLOWED_ROUTES:
        state.setdefault("history", []).append(
            f"[route_decision] invalid route '{route}' -> fallback retrieval_worker"
        )
        return "retrieval_worker"
    return route  # type: ignore[return-value]


# -----------------------------------------------------------------------------
# 3. Human review placeholder
# -----------------------------------------------------------------------------

def human_review_node(state: AgentState) -> AgentState:
    """
    HITL node: pause and wait for human approval.
    In this lab, keep it as a placeholder.
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered - awaiting human input")
    state["workers_called"].append("human_review")

    print("\n[HITL TRIGGERED]")
    print(f"  Task   : {_console_text(state['task'])}")
    print(f"  Reason : {_console_text(state['route_reason'])}")
    print("  Action : Auto-approving in lab mode\n")

    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved -> retrieval"
    return state


# -----------------------------------------------------------------------------
# 4. Worker wrappers
# Wrappers keep the graph boundary stable and guard worker failures.
# -----------------------------------------------------------------------------


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Wrapper for retrieval worker."""
    try:
        return retrieval_run(state)
    except Exception as error:
        return _record_worker_failure(
            state,
            worker_name="retrieval_worker",
            error_code="RETRIEVAL_FAILED",
            error=error,
            fallback_updates={
                "retrieved_chunks": [],
                "retrieved_sources": [],
            },
        )


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Wrapper for policy/tool worker."""
    try:
        return policy_tool_run(state)
    except Exception as error:
        return _record_worker_failure(
            state,
            worker_name="policy_tool_worker",
            error_code="POLICY_CHECK_FAILED",
            error=error,
            fallback_updates={
                "policy_result": {
                    "policy_applies": False,
                    "policy_name": "error_fallback",
                    "exceptions_found": [],
                    "source": [],
                    "policy_version_note": str(error),
                }
            },
        )


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Wrapper for synthesis worker."""
    try:
        return synthesis_run(state)
    except Exception as error:
        return _record_worker_failure(
            state,
            worker_name="synthesis_worker",
            error_code="SYNTHESIS_FAILED",
            error=error,
            fallback_updates={
                "final_answer": (
                    f"[SYNTHESIS ERROR] Khong the tao cau tra loi: {error}"
                ),
                "sources": [],
                "confidence": 0.0,
            },
        )


# -----------------------------------------------------------------------------
# 5. Build graph
# -----------------------------------------------------------------------------

def build_graph():
    """
    Build the supervisor-worker graph.

    Option A: simple Python orchestrator (default for this lab).
    Option B: replace with LangGraph later if needed.
    """

    def run(state: AgentState) -> AgentState:
        import time

        start = time.time()

        state = supervisor_node(state)
        route = route_decision(state)

        if route == "human_review":
            state = human_review_node(state)
            state = retrieval_worker_node(state)
        elif route == "policy_tool_worker":
            state = policy_tool_worker_node(state)
            if not state["retrieved_chunks"]:
                state = retrieval_worker_node(state)
        else:
            state = retrieval_worker_node(state)

        state = synthesis_worker_node(state)
        state["latency_ms"] = int((time.time() - start) * 1000)
        state["history"].append(f"[graph] completed in {state['latency_ms']}ms")
        return state

    return run


# -----------------------------------------------------------------------------
# 6. Public API
# -----------------------------------------------------------------------------

_graph = build_graph()


def run_graph(task: str) -> AgentState:
    """Entry point for one full graph run."""
    state = make_initial_state(task)
    return _graph(state)


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Save trace to JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    return filename


# -----------------------------------------------------------------------------
# 7. Manual test
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print("Day 09 Lab - Supervisor-Worker Graph")
    print("=" * 60)

    test_queries = [
        "SLA xu ly ticket P1 la bao lau?",
        "Khach hang Flash Sale yeu cau hoan tien vi san pham loi - duoc khong?",
        "Can cap quyen Level 3 de khac phuc P1 khan cap. Quy trinh la gi?",
    ]

    for query in test_queries:
        print(f"\n> Query: {_console_text(query)}")
        result = run_graph(query)
        print(f"  Route      : {_console_text(result['supervisor_route'])}")
        print(f"  Reason     : {_console_text(result['route_reason'])}")
        print(f"  Workers    : {_console_text(result['workers_called'])}")
        print(f"  Answer     : {_console_text(result['final_answer'][:100])}...")
        print(f"  Confidence : {_console_text(result['confidence'])}")
        print(f"  Latency    : {_console_text(result['latency_ms'])}ms")
        trace_file = save_trace(result)
        print(f"  Trace saved: {_console_text(trace_file)}")

    print("\nGraph smoke test complete.")
