"""A minimal MCP server (Streamable HTTP, JSON responses) that puts Waypoint in front of an agent.

An agent connects once and sees two tools instead of the whole catalog: `find_tools` returns the
schemas of the few tools a task needs, and `report_run` writes the run's outcome back into the
graph so the next route is better. JSON-RPC is handled here by hand to keep the app dependency-free.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from hydrahack.data import Api

SUPPORTED = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26"]
_PARAMS = re.compile(
    r"(required|optional)_params: (\[.*?\])(?=, (?:optional_params|return_schema))", re.S
)
_TYPES = {"STRING": "string", "NUMBER": "number", "BOOLEAN": "boolean", "ARRAY": "array"}

TOOLS = [
    {
        "name": "find_tools",
        "description": (
            "Find the few tools a task needs out of a catalog of 1,419 APIs. Returns their names, "
            "descriptions and input schemas, ranked by Waypoint's experience graph in HydraDB. "
            "Call this before planning, then call report_run when the task is done."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The user's task in plain language"},
                "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            "required": ["task"],
        },
    },
    {
        "name": "report_run",
        "description": (
            "Tell Waypoint which tools the finished task actually needed (by the ids find_tools "
            "returned). It writes the run into the graph, so similar tasks route better next time."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "used": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                "offered": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["task", "used"],
        },
    },
]


def tool_schema(api: Api) -> dict[str, Any]:
    """The catalog entry as an MCP-style tool definition with a JSON Schema for its inputs."""
    props: dict[str, Any] = {}
    required: list[str] = []
    for kind, raw in _PARAMS.findall(api.text):
        try:
            params = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for p in params:
            name = str(p.get("name", "")).strip()
            if not name:
                continue
            props[name] = {
                "type": _TYPES.get(str(p.get("type", "")).upper(), "string"),
                "description": str(p.get("description", ""))[:300],
            }
            if kind == "required":
                required.append(name)
    return {
        "id": api.idx,
        "name": api.name,
        "server": api.tool,
        "category": api.category,
        "description": api.description[:500],
        "inputSchema": {"type": "object", "properties": props, "required": required},
    }


def _result(msg_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text(payload: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "structuredContent": payload,
    }


def handle(
    msg: dict,
    find_tools: Callable[[str, int], dict],
    report_run: Callable[[str, list[int], list[int]], dict],
) -> dict | None:
    """Answer one JSON-RPC message; notifications (no id) get None."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "invalid request")
    method, msg_id, params = msg["method"], msg.get("id"), msg.get("params") or {}
    if msg_id is None:
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(
            msg_id,
            {
                "protocolVersion": asked if asked in SUPPORTED else SUPPORTED[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "waypoint", "version": "0.1.0"},
                "instructions": "Call find_tools(task) first; call report_run when done.",
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        task = args.get("task")
        if not isinstance(task, str) or len(task.strip()) < 3:
            return _error(msg_id, -32602, "task must be a non-empty string")
        try:
            if name == "find_tools":
                k = int(args.get("k", 5))
                return _result(msg_id, _text(find_tools(task, max(1, min(k, 20)))))
            if name == "report_run":
                used = [int(a) for a in args.get("used") or []]
                offered = [int(a) for a in args.get("offered") or []]
                if not used:
                    return _error(msg_id, -32602, "used must list at least one tool id")
                return _result(msg_id, _text(report_run(task, used, offered)))
        except (TypeError, ValueError) as exc:
            return _error(msg_id, -32602, str(exc))
        return _error(msg_id, -32602, f"unknown tool: {name}")
    return _error(msg_id, -32601, f"method not found: {method}")
