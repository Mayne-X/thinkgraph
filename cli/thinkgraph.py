#!/usr/bin/env python3
"""
thinkgraph.py — Deterministic helper CLI for ThinkGraph skill.

Does ONLY bookkeeping: DAG validation, caching, token counting, normalization.
NEVER calls an LLM. All reasoning stays in the host agent.

Usage:
    python thinkgraph.py <command> [args...]

Commands:
    triage "prompt"                       Classify prompt complexity
    decompose "prompt" [--max-nodes N]    Emit DAG JSON
    validate-dag graph.json               Validate a DAG file
    normalize "question"                  Normalize + hash a question
    cache-get "question"                  Look up cached fact
    cache-set "question" "claim" [conf]   Store a cached fact
    aggregate facts.json                  Build synthesis fact-sheet
    tokens "text"                         Estimate token count
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_FILE = "thinkgraph.cache.json"
CONFIG_FILE = "thinkgraph.config.json"
DEFAULT_MAX_NODES = 5
DEFAULT_MAX_DEPTH = 2
TOKEN_RATIO = 4  # ~4 chars per token estimate
CACHE_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_question(question: str) -> str:
    """Normalize a question for cache keying."""
    q = question.lower()
    q = re.sub(r"[^\w\s]", "", q)       # strip punctuation
    q = re.sub(r"\s+", " ", q).strip()  # collapse spaces
    return q


def question_hash(question: str) -> str:
    """SHA-256 hash of normalized question, truncated to 16 chars."""
    normalized = normalize_question(question)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Heuristic token count (~4 chars per token)."""
    return max(1, len(text) // TOKEN_RATIO)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_path(project_root: Optional[str] = None) -> Path:
    """Resolve cache file path. Global cache at ~/.thinkgraph/cache.json,
    with project-local override if .pcg/ exists."""
    # Project-local override
    if project_root:
        return Path(project_root) / CACHE_FILE

    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".pcg").exists():
            return parent / CACHE_FILE

    # Global default
    global_dir = Path.home() / ".thinkgraph"
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir / CACHE_FILE


def _load_cache(project_root: Optional[str] = None) -> Dict[str, Any]:
    path = _cache_path(project_root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "entries": {}}
    return {"version": 1, "entries": {}}


def _save_cache(cache: Dict[str, Any], project_root: Optional[str] = None) -> None:
    path = _cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def cache_get(question: str, project_root: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Look up a cached fact by normalized question."""
    h = question_hash(question)
    cache = _load_cache(project_root)
    entry = cache.get("entries", {}).get(h)
    if not entry:
        return None

    # Check TTL
    if "resolved_at" in entry and "ttl_days" in entry:
        try:
            resolved = datetime.fromisoformat(entry["resolved_at"])
            ttl = entry["ttl_days"]
            if (datetime.now(timezone.utc) - resolved).days > ttl:
                return None  # expired
        except (ValueError, TypeError):
            pass

    return entry


def cache_set(
    question: str,
    claim: str,
    confidence: float = 0.9,
    source: str = "internal",
    project_root: Optional[str] = None,
) -> dict:
    """Store a fact in the cache."""
    h = question_hash(question)
    cache = _load_cache(project_root)
    cache.setdefault("entries", {})[h] = {
        "question": normalize_question(question),
        "claim": claim,
        "confidence": confidence,
        "source": source,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "ttl_days": CACHE_TTL_DAYS,
    }
    _save_cache(cache, project_root)
    return cache["entries"][h]


# ---------------------------------------------------------------------------
# DAG validation
# ---------------------------------------------------------------------------

class DAGValidationError(Exception):
    pass


def validate_dag(dag: Dict[str, Any]) -> List[List[str]]:
    """Validate a DAG and return execution batches (topological sort).

    Raises DAGValidationError on invalid DAG.
    Returns list of batches, where each batch is a list of node IDs
    that can execute in parallel.
    """
    nodes = dag.get("nodes", [])
    if not nodes:
        return []

    node_ids = {n["id"] for n in nodes}
    edges = dag.get("edges", [])

    # Validate node structure
    for node in nodes:
        if "id" not in node or "q" not in node or "deps" not in node:
            raise DAGValidationError(
                f"Node missing required fields (id, q, deps): {node}"
            )
        if not re.match(r"^Q\d+$", node["id"]):
            raise DAGValidationError(
                f"Node ID must match ^Q\\d+$, got: {node['id']}"
            )

    # Validate edges
    for edge in edges:
        if len(edge) != 2:
            raise DAGValidationError(f"Edge must be [from, to]: {edge}")
        if edge[0] not in node_ids:
            raise DAGValidationError(f"Edge references unknown node: {edge[0]}")
        if edge[1] not in node_ids:
            raise DAGValidationError(f"Edge references unknown node: {edge[1]}")

    # Validate deps in nodes
    for node in nodes:
        for dep in node["deps"]:
            if dep not in node_ids:
                raise DAGValidationError(
                    f"Node {node['id']} depends on unknown node: {dep}"
                )
            if dep == node["id"]:
                raise DAGValidationError(
                    f"Node {node['id']} depends on itself"
                )

    # Topological sort with cycle detection
    in_degree = {nid: 0 for nid in node_ids}
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}

    for node in nodes:
        for dep in node["deps"]:
            adj[dep].append(node["id"])
            in_degree[node["id"]] += 1

    # Also incorporate explicit edges
    for fr, to in edges:
        if to not in adj[fr]:
            adj[fr].append(to)
            in_degree[to] += 1

    queue = [nid for nid in node_ids if in_degree[nid] == 0]
    order: list[str] = []
    batches: List[List[str]] = []

    while queue:
        batch = sorted(queue)  # deterministic ordering
        batches.append(batch)
        queue = []
        for nid in batch:
            order.append(nid)
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

    if len(order) != len(node_ids):
        missing = node_ids - set(order)
        raise DAGValidationError(
            f"Cycle detected involving nodes: {missing}"
        )

    max_depth_reached = _calc_depth(nodes) if node_ids else 0

    return batches


def _calc_depth(nodes: List[Dict[str, Any]]) -> int:
    """Calculate max depth of a DAG's nodes list."""
    depth_map: Dict[str, int] = {}

    def _depth(nid: str) -> int:
        if nid in depth_map:
            return depth_map[nid]
        node = next((n for n in nodes if n["id"] == nid), None)
        if not node or not node["deps"]:
            depth_map[nid] = 0
            return 0
        d = 1 + max((_depth(dep) for dep in node["deps"]), default=0)
        depth_map[nid] = d
        return d

    return max((_depth(n["id"]) for n in nodes), default=0) if nodes else 0


def validate_dag_file(filepath: str, max_depth: int = DEFAULT_MAX_DEPTH) -> dict:
    """Validate a DAG from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise DAGValidationError(f"File not found: {filepath}")

    try:
        dag = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise DAGValidationError(f"Invalid JSON: {e}")

    batches = validate_dag(dag)
    nodes = dag.get("nodes", [])
    actual_depth = _calc_depth(nodes)

    if actual_depth > max_depth:
        raise DAGValidationError(
            f"Depth {actual_depth} exceeds max {max_depth}"
        )

    return {
        "valid": True,
        "node_count": len(nodes),
        "batch_count": len(batches),
        "batches": batches,
        "max_depth_reached": actual_depth,
    }


# ---------------------------------------------------------------------------
# Triage (heuristic, no LLM)
# ---------------------------------------------------------------------------

# Simple keyword-based triage. The agent should use the LLM prompt for
# accurate triage. This is a fast heuristic fallback.

COMPLEXITY_SIGNALS = {
    "multi_hop": [
        "compare", "contrast", "difference between", "vs", "versus",
        "pros and cons", "trade-off", "tradeoffs",
    ],
    "planning": [
        "plan", "design", "architect", "strategy", "approach",
        "how should", "step by step", "roadmap",
    ],
    "evaluation": [
        "evaluate", "assess", "review", "critique", "analyze",
        "analyse", "what are the implications",
    ],
    "constraint": [
        "given that", "assuming", "constraint", "requirement",
        "must", "should", "cannot",
    ],
}


def triage_heuristic(prompt: str) -> str:
    """Quick heuristic triage. Returns: trivial, single_hop, multi_hop, planning, creative."""
    prompt_lower = prompt.lower().strip()

    # Very short = trivial
    if len(prompt_lower.split()) < 8:
        return "trivial"

    # Check for complexity signals
    for category, signals in COMPLEXITY_SIGNALS.items():
        for signal in signals:
            if signal in prompt_lower:
                if category in ("multi_hop", "constraint"):
                    return "multi_hop"
                elif category in ("planning", "evaluation"):
                    return "planning"

    # Check for "and" splitting multiple questions
    if " and " in prompt_lower:
        # Could be multi-hop if the "and" joins independent facts
        parts = prompt_lower.split(" and ")
        if len(parts) >= 2 and any(
            len(p.split()) > 5 for p in parts
        ):
            return "multi_hop"

    return "single_hop"


# ---------------------------------------------------------------------------
# Aggregate facts
# ---------------------------------------------------------------------------

def aggregate_facts(facts_path: str) -> str:
    """Build a confidence-weighted fact-sheet from a JSON array of facts."""
    path = Path(facts_path)
    if not path.exists():
        raise FileNotFoundError(f"Facts file not found: {facts_path}")

    facts = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(facts, list):
        raise ValueError("Facts file must contain a JSON array")

    # Sort by confidence descending
    facts.sort(key=lambda f: f.get("confidence", 0), reverse=True)

    lines = []
    for fact in facts:
        q_id = fact.get("id", "?")
        claim = fact.get("claim", "unknown")
        conf = fact.get("confidence", 0.0)
        source = fact.get("source", "internal")
        parents = fact.get("parent", None)

        note = ""
        if conf < 0.6:
            note = " ⚠️ low-confidence"
        elif conf < 0.8:
            note = " (moderate confidence)"
        if parents:
            note += f", derived from {parents}"

        lines.append(f"{q_id} → {claim} (conf: {conf:.2f}{note})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_triage(args):
    result = triage_heuristic(args.prompt)
    print(json.dumps({"classification": result, "prompt_tokens": estimate_tokens(args.prompt)}))


def cmd_decompose(args):
    # Decompose is primarily done by the LLM. This outputs the schema
    # constraint for the agent to follow.
    print(json.dumps({
        "max_nodes": args.max_nodes,
        "max_depth": args.max_depth,
        "schema_hint": {
            "nodes": [{"id": "Q1", "q": "...", "deps": []}],
        },
        "instructions": (
            "Emit a JSON DAG with nodes (id, q, deps) and edges. "
            f"Max {args.max_nodes} nodes, max depth {args.max_depth}. "
            "Each node is ONE atomic question."
        ),
    }))


def cmd_validate_dag(args):
    try:
        result = validate_dag_file(args.file, args.max_depth)
        print(json.dumps(result, indent=2))
    except DAGValidationError as e:
        print(json.dumps({"valid": False, "error": str(e)}), file=sys.stderr)
        sys.exit(1)


def cmd_normalize(args):
    h = question_hash(args.question)
    print(json.dumps({
        "normalized": normalize_question(args.question),
        "hash": h,
    }))


def cmd_cache_get(args):
    entry = cache_get(args.question, args.project_root)
    if entry:
        print(json.dumps(entry, indent=2))
    else:
        print(json.dumps({"found": False, "question": args.question}))
        sys.exit(1)


def cmd_cache_set(args):
    conf = args.confidence if args.confidence is not None else 0.9
    entry = cache_set(args.question, args.claim, conf, args.source, args.project_root)
    print(json.dumps({"stored": True, "hash": question_hash(args.question), "entry": entry}))


def cmd_tokens(args):
    count = estimate_tokens(args.text)
    print(json.dumps({"tokens": count, "chars": len(args.text)}))


def cmd_aggregate(args):
    sheet = aggregate_facts(args.file)
    print(sheet)


def main():
    parser = argparse.ArgumentParser(
        prog="thinkgraph",
        description="ThinkGraph helper CLI — deterministic bookkeeping only",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # triage
    p_triage = sub.add_parser("triage", help="Classify prompt complexity")
    p_triage.add_argument("prompt", help="User prompt to classify")
    p_triage.set_defaults(func=cmd_triage)

    # decompose
    p_decompose = sub.add_parser("decompose", help="Decomposition schema hint")
    p_decompose.add_argument("prompt", help="User prompt to decompose")
    p_decompose.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    p_decompose.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    p_decompose.set_defaults(func=cmd_decompose)

    # validate-dag
    p_validate = sub.add_parser("validate-dag", help="Validate a DAG JSON file")
    p_validate.add_argument("file", help="Path to DAG JSON file")
    p_validate.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    p_validate.set_defaults(func=cmd_validate_dag)

    # normalize
    p_norm = sub.add_parser("normalize", help="Normalize + hash a question")
    p_norm.add_argument("question", help="Question to normalize")
    p_norm.set_defaults(func=cmd_normalize)

    # cache-get
    p_cget = sub.add_parser("cache-get", help="Look up cached fact")
    p_cget.add_argument("question", help="Question to look up")
    p_cget.add_argument("--project-root", help="Project root directory")
    p_cget.set_defaults(func=cmd_cache_get)

    # cache-set
    p_cset = sub.add_parser("cache-set", help="Store a cached fact")
    p_cset.add_argument("question", help="Question (will be normalized)")
    p_cset.add_argument("claim", help="Factual answer")
    p_cset.add_argument("confidence", type=float, nargs="?", default=0.9)
    p_cset.add_argument("--source", default="internal", help="Source type")
    p_cset.add_argument("--project-root", help="Project root directory")
    p_cset.set_defaults(func=cmd_cache_set)

    # aggregate
    p_agg = sub.add_parser("aggregate", help="Build synthesis fact-sheet")
    p_agg.add_argument("file", help="Path to facts JSON array")
    p_agg.set_defaults(func=cmd_aggregate)

    # tokens
    p_tok = sub.add_parser("tokens", help="Estimate token count")
    p_tok.add_argument("text", help="Text to count tokens for")
    p_tok.set_defaults(func=cmd_tokens)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
