---
name: thinkgraph
description: Use for complex, multi-hop, or constraint-satisfaction questions. Decomposes into a DAG of atomic facts, resolves them, synthesizes a grounded answer. Includes self-consistency voting, web grounding, and MCP server. Skip for trivial lookups, chitchat, or small code edits. Trigger on: compare, plan, analyze, evaluate, design, trade-off.
---

# thinkgraph

Structured decomposition for complex prompts. Forces fact-grounded answering before guessing.

## Skip if

- Single factual lookup ("what is X?")
- Single inference step
- Chitchat or small code edits

## Protocol

### 1. Triage

Classify: **trivial** | **single-hop** | **multi-hop** | **planning** | **creative**

Trivial/single-hop/creative → answer directly, exit.

If borderline, ask: **"Run ThinkGraph? [Yes / Skip]"**

### 2. Decompose

Emit a DAG of atomic sub-questions:

```json
{"nodes": [{"id": "Q1", "q": "one atomic fact", "deps": []}]}
```

Rules:
- Each node = ONE fact, not compound
- Max 5 nodes, depth ≤ 2
- Leaf nodes resolve in parallel
- If the prompt is already atomic, skip decomposition

### 3. Resolve

For each node in topological order:
1. Check cache (normalize → hash → lookup)
2. Resolve: `{"claim": "...", "confidence": 0.0-1.0, "source": "internal"}`
3. If confidence < 0.6: handle per user config:
   - **Web search**: use `thinkgraph.py web-search "query"` (DuckDuckGo, no API key)
   - **Ask me**: present the sub-question to the user
   - **Best-guess**: proceed but mark fact as uncertain in synthesis
   - **Skip**: exclude this node and its dependents
4. Cache result
5. Early exit if answer already emerges from resolved facts

Budget: ≤300 tokens per node (in+out).

### 4. Self-Consistency Voting (on final synthesis)

Before presenting the final answer on high-stakes questions, run 2-3 synthesis attempts and vote:

```bash
python thinkgraph.py vote "answer v1" "answer v2" "answer v3"
```

Uses Jaccard similarity to find the centroid (most self-consistent) response.

### 5. Synthesize

Build fact-sheet (one line per node), then answer using ONLY verified facts:

```
Q1 → [fact] (conf: 0.95)
Q2 → [fact] (conf: 0.72, derived from Q1)
```

- Flag gaps and low-confidence items
- If budget exceeds 4× direct cost, abort to direct answer

### 6. Present

- High confidence: answer directly
- Low confidence present: append uncertainty note
- Self-consistency used: note it
- Skipped nodes: note missing parts

## Token budgets

| Stage | Max |
|---|---|
| Triage | 50 |
| Decompose | 200 |
| Per node | 300 |
| Synthesize | 600 |
| Ceiling | 4× direct cost |

## CLI commands

```bash
python thinkgraph.py triage "prompt"
python thinkgraph.py validate-dag graph.json
python thinkgraph.py cache-get "question"
python thinkgraph.py vote "r1" "r2" "r3"
python thinkgraph.py web-search "query"
python thinkgraph.py tokens "text"
```

## MCP server

```bash
python mcp/thinkgraph_mcp.py
```

Configure in your MCP client as a stdio server with command: `python /path/to/mcp/thinkgraph_mcp.py`

Tools: triage, validate-dag, vote, web-search, cache-get, cache-set, tokens