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
    normalize "question"                   Normalize + hash a question
    cache-get "question"                   Look up cached fact
    cache-set "question" "claim" [conf]   Store a cached fact
    aggregate facts.json                   Build synthesis fact-sheet
    tokens "text"                          Estimate token count
    vote "resp1" "resp2" [...]             Self-consistency voting (pick most consistent)
    web-search "query" [--num-results N]  Web search via DuckDuckGo HTML
    compress "file" [--ratio R]             Compress text via TF-IDF sentence extraction
    export facts.json --format [json|yaml|markdown]   Export results
    prune-dag graph.json --facts facts.json [--prompt "..."]  Dynamic DAG pruning
    ab-score "answer" [--ground-truth "..."]  Score answer quality (A/B testing)
    plugin-list                            List registered custom plugins
    plugin-register "name" "py_code"        Register a custom plugin
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Precompiled regex patterns — compile once, reuse everywhere
_RE_WORDS = re.compile(r"\w+")
_RE_PUNCT = re.compile(r"[^\w\s]")
_RE_SPACES = re.compile(r"\s+")
_RE_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CACHE_FILE = "thinkgraph.cache.json"
DEFAULT_MAX_NODES = 5
DEFAULT_MAX_DEPTH = 2
TOKEN_RATIO = 4  # ~4 chars per token estimate
CACHE_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Normalization (memoized for repeated same questions)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1024)
def normalize_question(question: str) -> str:
    """Normalize a question for cache keying. Sorted for reorder-insensitivity."""
    words = _RE_WORDS.findall(question.lower())
    return " ".join(sorted(words))


@lru_cache(maxsize=2048)
def question_hash(question: str) -> str:
    """SHA-256 hash of normalized question, truncated to 16 chars."""
    normalized = normalize_question(question)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Token estimation (memoized)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def estimate_tokens(text: str) -> int:
    """Heuristic token count (~4 chars per token)."""
    return max(1, len(text) // TOKEN_RATIO)


# ---------------------------------------------------------------------------
# Cache (global cache at ~/.thinkgraph/, project-local via .pcg/)
# ---------------------------------------------------------------------------

def _cache_path(project_root: Optional[str] = None) -> Path:
    if project_root:
        return Path(project_root) / CACHE_FILE
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".pcg").exists():
            return parent / CACHE_FILE
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

        lines.append(f"{q_id} -> {claim} (conf: {conf:.2f}{note})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt compression (TF-IDF sentence extraction, stdlib only)
# ---------------------------------------------------------------------------

def tokenize_sentences(text: str) -> List[str]:
    """Split text into sentences (uses precompiled regex)."""
    return [s.strip() for s in _RE_SENTENCE_END.split(text.strip()) if s.strip()]


@lru_cache(maxsize=512)
def compute_term_freq(text: str) -> Tuple[Tuple[str, float], ...]:
    """Compute TF (term frequency) as a sorted tuple of (word, tf) pairs.
    Cached per unique text."""
    words = _RE_WORDS.findall(text.lower())
    if not words:
        return ()
    tf_map: Dict[str, float] = {}
    for w in words:
        tf_map[w] = tf_map.get(w, 0.0) + 1.0
    total = len(words)
    return tuple((w, count / total) for w, count in tf_map.items())


def compress_sentences(text: str, target_ratio: float = 0.4) -> str:
    """Compress text by extracting top sentences via TF-IDF.
    Uses precompiled regex and cached term frequency lookups."""
    sentences = tokenize_sentences(text)
    n = len(sentences)
    if n <= 2:
        return text

    # Build IDF in one pass (no per-word re-scanning)
    word_doc_freq: Dict[str, int] = {}
    for s in sentences:
        unique_words = set(_RE_WORDS.findall(s.lower()))
        for w in unique_words:
            word_doc_freq[w] = word_doc_freq.get(w, 0) + 1

    n_float = float(n)
    idf: Dict[str, float] = {
        w: math.log((n_float + 1) / (df + 1)) + 1
        for w, df in word_doc_freq.items()
    }

    # Score each sentence (use cached TF lookups)
    scored: List[Tuple[float, str]] = []
    for s in sentences:
        tf_pairs = compute_term_freq(s)
        score = sum(tf * idf.get(w, 0.0) for w, tf in tf_pairs)
        scored.append((score, s))

    n_keep = max(1, int(n * target_ratio))
    kept = {s for score, s in sorted(scored, reverse=True)[:n_keep]}
    return " ".join(s for s in sentences if s in kept)


# ---------------------------------------------------------------------------
# Export formats (JSON, YAML, Markdown)
# ---------------------------------------------------------------------------

def export_results(
    dag: Dict[str, Any],
    facts: List[Dict[str, Any]],
    synthesis: str,
    output_format: str = "json",
) -> str:
    """Export pipeline results in the requested format.

    dag: the decomposition DAG
    facts: resolved facts per node
    synthesis: final synthesized answer
    """
    if output_format == "json":
        return json.dumps({
            "dag": dag,
            "facts": facts,
            "synthesis": synthesis,
        }, indent=2, ensure_ascii=False)

    elif output_format == "yaml":
        # Pure Python YAML emitter (no PyYAML dependency)
        def to_yaml(obj: Any, indent: int = 0) -> str:
            lines: List[str] = []
            prefix = "  " * indent
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (dict, list)) and v:
                        lines.append(f"{prefix}{k}:")
                        lines.append(to_yaml(v, indent + 1))
                    else:
                        safe = json.dumps(v) if not isinstance(v, str) else v
                        lines.append(f"{prefix}{k}: {safe}")
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        lines.append(f"{prefix}-")
                        lines.append(to_yaml(item, indent + 1))
                    else:
                        lines.append(f"{prefix}- {item}")
            return "\n".join(lines)

        return to_yaml({
            "dag": dag,
            "facts": facts,
            "synthesis": synthesis,
        })

    elif output_format == "markdown":
        lines = [
            "# ThinkGraph Pipeline Results",
            "",
            "## Decomposition",
            "",
        ]
        for node in dag.get("nodes", []):
            qid = node["id"]
            deps = node.get("deps", [])
            facts_for_q = [f for f in facts if f.get("id") == qid]
            lines.append(f"### {qid}: {node['q']}")
            if deps:
                lines.append(f"_Depends on: {', '.join(deps)}_")
            for f in facts_for_q:
                conf = f.get("confidence", 0.0)
                warn = " ⚠️" if conf < 0.6 else ""
                lines.append(f"- **{f.get('claim', 'unknown')}** (conf: {conf:.2f}){warn}")
            lines.append("")

        lines.extend([
            "## Synthesis",
            "",
            synthesis,
        ])
        return "\n".join(lines)

    else:
        raise ValueError(f"Unknown export format: {output_format}. Use: json, yaml, markdown")


# ---------------------------------------------------------------------------
# Dynamic DAG pruning
# ---------------------------------------------------------------------------

def prune_dag(
    dag: Dict[str, Any],
    resolved_facts: Dict[str, Dict[str, Any]],
    main_prompt: str,
) -> Dict[str, Any]:
    """Remove nodes that are no longer relevant after parent facts are resolved.

    Heuristic: if a node's claim already satisfies a sub-concept that was
    implicitly part of the main prompt, prune its dependents if they would
    ask for information already covered by the parent claim.

    Returns a pruned copy of the DAG (does not mutate original).
    """
    nodes = dag.get("nodes", [])
    if not nodes:
        return dag

    # Build a "covered concepts" set from resolved parent claims
    covered_terms: Set[str] = set()
    for node_id, fact in resolved_facts.items():
        claim = fact.get("claim", "").lower()
        covered_terms.update(re.findall(r"\w+", claim))

    # For each unresolved node, check if all its parent claims together
    # already imply the answer (covered terms overlap significantly)
    pruned_node_ids: Set[str] = set()

    for node in nodes:
        node_id = node["id"]
        if node_id in resolved_facts:
            continue  # already resolved, skip

        deps = node.get("deps", [])
        if not deps:
            continue  # root nodes are never pruned

        # Get combined covered terms from all resolved parents
        parent_terms: Set[str] = set()
        all_parents_resolved = all(d in resolved_facts for d in deps)
        if not all_parents_resolved:
            continue  # can't evaluate unresolved parents

        for d in deps:
            if d in resolved_facts:
                parent_claim = resolved_facts[d].get("claim", "").lower()
                parent_terms.update(re.findall(r"\w+", parent_claim))

        # Get node question terms
        node_terms = set(re.findall(r"\w+", node["q"].lower()))

        # If node's question terms are mostly covered by parent claims, prune
        overlap = node_terms & parent_terms
        coverage = len(overlap) / len(node_terms) if node_terms else 0.0

        if coverage >= 0.75:  # 75% of question terms already answered by parents
            pruned_node_ids.add(node_id)

    # Return pruned DAG
    if not pruned_node_ids:
        return dag

    remaining_nodes = [n for n in nodes if n["id"] not in pruned_node_ids]
    remaining_ids = {n["id"] for n in remaining_nodes}

    # Remove edges referencing pruned nodes
    edges = [
        e for e in dag.get("edges", [])
        if e[0] in remaining_ids and e[1] in remaining_ids
    ]

    # Remove deps referencing pruned nodes
    for n in remaining_nodes:
        n["deps"] = [d for d in n.get("deps", []) if d in remaining_ids]

    return {
        "nodes": remaining_nodes,
        "edges": edges,
        "_pruned": list(pruned_node_ids),
    }


# ---------------------------------------------------------------------------
# Plugin hooks for custom resolve functions
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Registry for custom resolve functions (API calls, DB lookups, etc.)."""

    _hooks: Dict[str, callable] = {}

    @classmethod
    def register(cls, name: str, fn: callable) -> None:
        cls._hooks[name] = fn

    @classmethod
    def resolve(cls, name: str, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if name not in cls._hooks:
            return {"error": f"No plugin registered: {name}"}
        try:
            result = cls._hooks[name](question, context)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def list_plugins(cls) -> List[str]:
        return list(cls._hooks.keys())

    @classmethod
    def clear(cls) -> None:
        cls._hooks.clear()


def register_plugin(name: str, fn: callable) -> None:
    """Decorator/utility to register a custom resolve function.

    Function signature: fn(question: str, context: dict) -> dict
    The returned dict should have at least {"claim": "...", "confidence": 0.0-1.0}

    Example:
        @register_plugin("fetch_from_api")
        def fetch_weather(question, ctx):
            location = extract_location(question)
            data = api.get(f"/weather/{location}")
            return {"claim": f"weather is {data['temp']}C", "confidence": 0.95}
    """
    PluginRegistry.register(name, fn)


# Built-in shell-command plugin
def shell_resolve(question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Plugin: run a shell command and parse its output as the answer."""
    cmd = context.get("command", "")
    import subprocess
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip()
        return {
            "claim": output if output else "(no output)",
            "confidence": 0.9 if result.returncode == 0 else 0.5,
            "source": "shell",
        }
    except Exception as e:
        return {"claim": f"(command failed: {e})", "confidence": 0.0, "source": "shell"}


def weblookup_resolve(question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Plugin: look up a fact via web search."""
    num_results = context.get("num_results", 3)
    result = web_search(question, num_results=num_results)
    results = result.get("results", [])
    if not results:
        return {"claim": "(no web results found)", "confidence": 0.3, "source": "web"}
    top = results[0]
    claim = f"{top['title']}: {top['snippet'][:200]}" if top.get("snippet") else top.get("title", "")
    return {"claim": claim, "confidence": 0.75, "source": "web", "url": top.get("url", "")}


# Pre-register built-in plugins
PluginRegistry.register("shell", shell_resolve)
PluginRegistry.register("weblookup", weblookup_resolve)


# ---------------------------------------------------------------------------
# A/B testing mode
# ---------------------------------------------------------------------------

def ab_score(answer: str, ground_truth: Optional[str] = None) -> Dict[str, Any]:
    """Score an answer for A/B testing mode.

    If ground_truth is provided: exact match + keyword overlap with ground truth.
    If not: returns structural quality metrics (length, claim count, uncertainty flags).
    """
    words = set(re.findall(r"\w+", answer.lower()))

    # Count uncertainty markers
    uncertainty_markers = re.findall(
        r"\b(maybe|perhaps|possibly|might|could be|likely|probably|not sure|uncertain)\b",
        answer.lower(),
    )

    # Count claim sentences (sentences ending with period that aren't questions)
    claim_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", answer)
        if s.strip() and not s.strip().endswith("?")
    ]

    score = {
        "word_count": len(answer.split()),
        "claim_count": len(claim_sentences),
        "uncertainty_flags": len(uncertainty_markers),
        "has_uncertainty": len(uncertainty_markers) > 0,
        "unique_words": len(words),
        "vocabulary_richness": round(len(words) / max(1, len(answer.split())), 3),
    }

    if ground_truth:
        gt_words = set(re.findall(r"\w+", ground_truth.lower()))
        overlap = words & gt_words
        score["keyword_recall"] = round(len(overlap) / len(gt_words), 3) if gt_words else 0.0
        score["precision"] = round(len(overlap) / len(words), 3) if words else 0.0
        score["ground_truth_provided"] = True
    else:
        score["ground_truth_provided"] = False

    return score


# ---------------------------------------------------------------------------
# Self-consistency voting
# ---------------------------------------------------------------------------

def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts based on word sets."""
    words1 = set(re.findall(r"\w+", text1.lower()))
    words2 = set(re.findall(r"\w+", text2.lower()))
    if not words1 and not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


def self_consistency_vote(responses: List[str]) -> Dict[str, Any]:
    """Pick the most self-consistent response from a list of LLM completions.

    Algorithm: pairwise Jaccard similarity. The response with the highest
    average similarity to all others is the most consistent (centroid).
    Returns the winner, score, and similarity matrix.
    """
    if not responses:
        return {"winner": "", "score": 0.0, "index": -1, "similarities": []}
    if len(responses) == 1:
        return {"winner": responses[0], "score": 1.0, "index": 0, "similarities": [1.0]}

    n = len(responses)
    scores: List[float] = []
    for i in range(n):
        sims = [jaccard_similarity(responses[i], responses[j]) for j in range(n) if j != i]
        scores.append(sum(sims) / len(sims) if sims else 0.0)

    best_idx = scores.index(max(scores))
    return {
        "winner": responses[best_idx],
        "score": round(scores[best_idx], 4),
        "index": best_idx,
        "all_scores": [round(s, 4) for s in scores],
        "response_count": n,
    }


# ---------------------------------------------------------------------------
# Web grounding (DuckDuckGo HTML search — zero API key, stdlib only)
# ---------------------------------------------------------------------------

def web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    """Search the web via DuckDuckGo HTML (no API key required).

    Returns a list of {title, url, snippet} dicts.
    Falls back gracefully if network is unavailable.
    """
    try:
        import urllib.request

        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        results: List[Dict[str, str]] = []
        # DuckDuckGo HTML result blocks
        # Each result: <a class="result__a" href="URL">TITLE</a>
        #              <a class="result__snippet" href="...">SNIPPET</a>
        import html as html_lib

        # Find result blocks
        raw_blocks = re.findall(
            r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            html,
        )
        snippet_blocks = re.findall(
            r'<a class="result__snippet"[^>]*>([^<]+)</a>',
            html,
        )

        for i, (url, title_raw) in enumerate(raw_blocks[:num_results]):
            title = html_lib.unescape(title_raw.strip())
            snippet = ""
            if i < len(snippet_blocks):
                snippet = html_lib.unescape(snippet_blocks[i].strip())
            results.append({"title": title, "url": url, "snippet": snippet})

        return {
            "query": query,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        return {
            "query": query,
            "count": 0,
            "results": [],
            "error": str(e),
        }


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


def cmd_vote(args):
    responses = [r.strip() for r in args.responses if r.strip()]
    result = self_consistency_vote(responses)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_web_search(args):
    result = web_search(args.query, num_results=args.num_results)
    print(f"Search: {result['query']}")
    if result.get("error"):
        print(f"  Error: {result['error']}")
    else:
        for r in result["results"]:
            print(f"  - {r['title']}")
            print(f"    {r['url']}")
            if r["snippet"]:
                print(f"    {r['snippet'][:150]}...")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_compress(args):
    raw = Path(args.file).read_text(encoding="utf-8-sig") if args.file != "-" else sys.stdin.read()
    raw = raw.lstrip("\ufeff").strip()  # strip BOM if present
    ratio = getattr(args, "ratio", 0.4)
    compressed = compress_sentences(raw, target_ratio=ratio)
    orig_words = len(raw.split())
    new_words = len(compressed.split())
    sys.stdout.write(f"Compressed: {orig_words} -> {new_words} words (kept {ratio:.0%})\n\n")
    sys.stdout.write(compressed + "\n")


def cmd_export(args):
    facts_path = Path(args.facts)
    if not facts_path.exists():
        raise FileNotFoundError(f"File not found: {args.facts}")
    data = json.loads(facts_path.read_text(encoding="utf-8"))
    dag = data.get("dag", {})
    facts = data.get("facts", [])
    synthesis = data.get("synthesis", "")
    output = export_results(dag, facts, synthesis, output_format=args.format)
    print(output)


def cmd_prune_dag(args):
    dag_path = Path(args.file)
    dag = json.loads(dag_path.read_text(encoding="utf-8-sig"))
    facts: Dict[str, Dict[str, Any]] = {}
    if args.facts:
        facts_data = json.loads(Path(args.facts).read_text(encoding="utf-8-sig"))
        for f in facts_data:
            facts[f.get("id", "")] = f
    main_prompt = args.prompt or ""
    pruned = prune_dag(dag, facts, main_prompt)
    sys.stdout.write(json.dumps(pruned, indent=2, ensure_ascii=False) + "\n")


def cmd_ab_score(args):
    score = ab_score(args.answer, ground_truth=args.ground_truth)
    print(json.dumps(score, indent=2))
    if score["ground_truth_provided"]:
        print(f"Keyword recall: {score['keyword_recall']:.2%}")
        print(f"Precision: {score['precision']:.2%}")
    else:
        print(f"Claim count: {score['claim_count']}, Uncertainty flags: {score['uncertainty_flags']}")


def cmd_plugin_list(args):
    plugins = PluginRegistry.list_plugins()
    if not plugins:
        print("No plugins registered.")
    for name in plugins:
        print(f"  - {name}")


def cmd_plugin_register(args):
    name = args.name
    # Execute the provided Python code and register the resulting function
    namespace: Dict[str, Any] = {}
    try:
        exec(args.py_code, namespace)
        fn = namespace.get(name) or namespace.get("fn", None)
        if callable(fn):
            PluginRegistry.register(name, fn)
            print(f"Registered plugin: {name}")
        else:
            print(f"Error: no callable found in provided code for '{name}'")
            sys.exit(1)
    except Exception as e:
        print(f"Error registering plugin: {e}")
        sys.exit(1)


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

    # vote (self-consistency)
    p_vote = sub.add_parser("vote", help="Self-consistency voting — pick most consistent response")
    p_vote.add_argument("responses", nargs="+", help="Multiple LLM responses to compare")
    p_vote.set_defaults(func=cmd_vote)

    # web-search
    p_search = sub.add_parser("web-search", help="Web search via DuckDuckGo HTML (no API key)")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--num-results", type=int, default=5, help="Number of results (default: 5)")
    p_search.set_defaults(func=cmd_web_search)

    # compress
    p_compress = sub.add_parser("compress", help="Compress text via TF-IDF sentence extraction")
    p_compress.add_argument("file", help="File to compress, or '-' for stdin")
    p_compress.add_argument("--ratio", type=float, default=0.4, help="Fraction of sentences to keep (default: 0.4)")
    p_compress.set_defaults(func=cmd_compress)

    # export
    p_export = sub.add_parser("export", help="Export pipeline results in various formats")
    p_export.add_argument("facts", help="Path to facts JSON file")
    p_export.add_argument("--format", default="markdown", choices=["json", "yaml", "markdown"], help="Output format (default: markdown)")
    p_export.set_defaults(func=cmd_export)

    # prune-dag
    p_prune = sub.add_parser("prune-dag", help="Dynamic DAG pruning — remove nodes whose parents answer them")
    p_prune.add_argument("file", help="Path to DAG JSON file")
    p_prune.add_argument("--facts", help="Path to resolved facts JSON")
    p_prune.add_argument("--prompt", default="", help="Original user prompt (for context)")
    p_prune.set_defaults(func=cmd_prune_dag)

    # ab-score
    p_ab = sub.add_parser("ab-score", help="Score answer quality for A/B testing")
    p_ab.add_argument("answer", help="Answer to score")
    p_ab.add_argument("--ground-truth", dest="ground_truth", default=None, help="Reference answer for keyword recall")
    p_ab.set_defaults(func=cmd_ab_score)

    # plugin-list
    p_pl = sub.add_parser("plugin-list", help="List registered custom plugins")
    p_pl.set_defaults(func=cmd_plugin_list)

    # plugin-register
    p_pr = sub.add_parser("plugin-register", help="Register a custom resolve plugin")
    p_pr.add_argument("name", help="Plugin name")
    p_pr.add_argument("py_code", help="Python code that defines a function with this name")
    p_pr.set_defaults(func=cmd_plugin_register)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
