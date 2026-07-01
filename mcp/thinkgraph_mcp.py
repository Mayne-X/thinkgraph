#!/usr/bin/env python3
"""
thinkgraph_mcp.py — MCP server for ThinkGraph.

Implements the Model Context Protocol (JSON-RPC 2.0 over stdio).
Exposes ThinkGraph's core functions as MCP tools to any MCP-compatible agent.

Run with:  python thinkgraph_mcp.py

Requires: Python 3.8+, stdlib only (no external dependencies).
"""

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import from sibling cli module
sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))
from thinkgraph import (
    cache_get,
    cache_set,
    estimate_tokens,
    self_consistency_vote,
    triage_heuristic,
    validate_dag,
    validate_dag_file,
    web_search,
    question_hash,
)


# ---------------------------------------------------------------------------
# MCP Protocol Helpers
# ---------------------------------------------------------------------------

def read_message() -> Optional[Dict[str, Any]]:
    """Read a single JSON-RPC message from stdin. Blocks until available."""
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line.strip())
    except (json.JSONDecodeError, OSError):
        return None


def send_response(req_id: Any, result: Any) -> None:
    """Send a JSON-RPC 2.0 response."""
    msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_error(req_id: Any, code: int, message: str, data: Any = None) -> None:
    """Send a JSON-RPC 2.0 error response."""
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    msg = {"jsonrpc": "2.0", "id": req_id, "error": err}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_notification(method: str, params: Dict[str, Any]) -> None:
    """Send a JSON-RPC 2.0 notification (no id)."""
    msg = {"jsonrpc": "2.0", "method": method, "params": params}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Tool Definitions (MCP schema)
# ---------------------------------------------------------------------------

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "thinkgraph_triage",
        "description": (
            "Classify a prompt as trivial, single-hop, multi-hop, planning, or creative. "
            "Returns the classification and estimated token count. "
            "Use for any prompt that might need multi-step reasoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The user prompt to classify",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "thinkgraph_validate_dag",
        "description": (
            "Validate a DAG (Directed Acyclic Graph) of sub-questions. "
            "Checks for cycles, depth violations, and structural issues. "
            "Returns execution batches (nodes that can run in parallel)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dag": {
                    "type": "object",
                    "description": "The DAG JSON with nodes (id, q, deps) and edges",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum allowed depth (default: 2)",
                    "default": 2,
                },
            },
            "required": ["dag"],
        },
    },
    {
        "name": "thinkgraph_vote",
        "description": (
            "Self-consistency voting: pick the most consistent response from multiple LLM completions. "
            "Uses Jaccard similarity to find the centroid response. "
            "Returns the winner, confidence score, and all pairwise scores."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "responses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of LLM response strings to compare",
                    "minItems": 2,
                },
            },
            "required": ["responses"],
        },
    },
    {
        "name": "thinkgraph_web_search",
        "description": (
            "Web search via DuckDuckGo HTML (no API key required). "
            "Returns top results with titles, URLs, and snippets. "
            "Use to ground low-confidence facts with real data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "thinkgraph_cache_get",
        "description": (
            "Look up a previously resolved fact from the ThinkGraph cache. "
            "Uses normalized question hashing for deduplication. "
            "Returns the cached fact and confidence, or null if not found."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to look up in cache",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "thinkgraph_cache_set",
        "description": (
            "Store a resolved fact in the ThinkGraph cache. "
            "The fact is normalized and hashed for consistent retrieval. "
            "Cached facts persist across sessions (TTL: 30 days)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The original question",
                },
                "claim": {
                    "type": "string",
                    "description": "The factual answer/claim",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0-1.0",
                    "default": 0.9,
                },
            },
            "required": ["question", "claim"],
        },
    },
    {
        "name": "thinkgraph_tokens",
        "description": "Estimate token count for a text string. Uses ~4 chars per token heuristic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to count tokens for"},
            },
            "required": ["text"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

def handle_triage(params: Dict[str, Any]) -> Dict[str, Any]:
    prompt = params.get("prompt", "")
    classification = triage_heuristic(prompt)
    tokens = estimate_tokens(prompt)
    return {"classification": classification, "tokens": tokens, "prompt": prompt}


def handle_validate_dag(params: Dict[str, Any]) -> Dict[str, Any]:
    dag = params.get("dag", {})
    max_depth = params.get("max_depth", 2)
    try:
        batches = validate_dag(dag)
        return {
            "valid": True,
            "node_count": len(dag.get("nodes", [])),
            "batch_count": len(batches),
            "batches": batches,
            "max_depth_reached": _calc_max_depth(dag),
            "dag": dag,
        }
    except Exception as e:
        return {"valid": False, "error": str(e), "dag": dag}


def _calc_max_depth(dag: Dict[str, Any]) -> int:
    nodes = dag.get("nodes", [])
    if not nodes:
        return 0
    depth_map: Dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in depth_map:
            return depth_map[nid]
        node = next((n for n in nodes if n["id"] == nid), None)
        if not node or not node.get("deps"):
            depth_map[nid] = 0
            return 0
        d = 1 + max(depth(dep) for dep in node["deps"])
        depth_map[nid] = d
        return d

    return max((depth(n["id"]) for n in nodes), default=0)


def handle_vote(params: Dict[str, Any]) -> Dict[str, Any]:
    responses = params.get("responses", [])
    return self_consistency_vote(responses)


def handle_web_search(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params.get("query", "")
    num_results = params.get("num_results", 5)
    return web_search(query, num_results=num_results)


def handle_cache_get(params: Dict[str, Any]) -> Dict[str, Any]:
    question = params.get("question", "")
    entry = cache_get(question)
    if entry:
        return {"found": True, "hash": question_hash(question), **entry}
    return {"found": False, "hash": question_hash(question), "question": question}


def handle_cache_set(params: Dict[str, Any]) -> Dict[str, Any]:
    question = params.get("question", "")
    claim = params.get("claim", "")
    confidence = params.get("confidence", 0.9)
    entry = cache_set(question, claim, confidence)
    return {"stored": True, "hash": question_hash(question), **entry}


def handle_tokens(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params.get("text", "")
    tokens = estimate_tokens(text)
    return {"tokens": tokens, "chars": len(text), "text": text[:100]}


# ---------------------------------------------------------------------------
# Request Router
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "thinkgraph_triage": handle_triage,
    "thinkgraph_validate_dag": handle_validate_dag,
    "thinkgraph_vote": handle_vote,
    "thinkgraph_web_search": handle_web_search,
    "thinkgraph_cache_get": handle_cache_get,
    "thinkgraph_cache_set": handle_cache_set,
    "thinkgraph_tokens": handle_tokens,
}


def handle_request(req: Dict[str, Any]) -> None:
    """Route a JSON-RPC request to the appropriate handler."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    # Handle method
    if method == "initialize":
        send_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "thinkgraph",
                "version": "1.0.0",
            },
        })

    elif method == "notifications/initialized":
        pass  # Acknowledged

    elif method == "tools/list":
        send_response(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name in TOOL_HANDLERS:
            try:
                result = TOOL_HANDLERS[tool_name](tool_args)
                send_response(req_id, {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False),
                        }
                    ]
                })
            except Exception as e:
                send_error(req_id, -32603, f"Tool error: {e}", {"tool": tool_name})
        else:
            send_error(req_id, -32602, f"Unknown tool: {tool_name}", {"tool": tool_name})

    elif method == "shutdown":
        send_response(req_id, {"shutdown": True})
        sys.exit(0)

    else:
        if req_id is not None:
            send_error(req_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Main server loop
# ---------------------------------------------------------------------------

def main():
    while True:
        msg = read_message()
        if msg is None:
            break
        handle_request(msg)


if __name__ == "__main__":
    main()