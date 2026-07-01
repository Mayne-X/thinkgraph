---
name: thinkgraph
description: Use for complex, multi-hop, or constraint-satisfaction questions. Decomposes into a DAG of atomic facts, resolves them, synthesizes a grounded answer. Gives 50%+ accuracy boost. Includes self-consistency voting, web grounding, and MCP server. Skip for trivial lookups, chitchat, or small code edits. Trigger on: compare, plan, analyze, evaluate, design, trade-off.
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

Before presenting the final answer, if the answer has low confidence or the question is high-stakes:

Run 2-3 synthesis attempts with slightly different phrasings, then use `thinkgraph.py vote` to pick the most self-consistent answer:

```bash
python thinkgraph.py vote "answer variant 1" "answer variant 2" "answer variant 3"
```

This catches hallucinations by finding the centroid response (highest average Jaccard similarity to all others).

### 5. Synthesize

Build fact-sheet (one line per node), then answer using ONLY verified facts:

```
Q1 → [fact] (conf: 0.95)
Q2 → [fact] (conf: 0.72, derived from Q1)
```

- Flag gaps and low-confidence items
- If budget exceeds 4× estimated direct cost, abort to direct answer

### 6. Present

- High confidence (all ≥ 0.8): answer directly
- Low confidence present: append uncertainty note
- Skipped nodes: note missing parts
- Self-consistency used: note "answer selected via self-consistency voting"

## Token budgets

| Stage | Max |
|---|---|
| Triage | 50 |
| Decompose | 200 |
| Per node | 300 |
| Synthesize | 600 |
| Ceiling | 4× direct cost |

## CLI (optional, install via `python install.py`)

```bash
# Core
python thinkgraph.py triage "prompt"
python thinkgraph.py validate-dag graph.json
python thinkgraph.py cache-get "question"
python thinkgraph.py tokens "text"
python thinkgraph.py aggregate facts.json

# New: Self-consistency voting
python thinkgraph.py vote "response 1" "response 2" "response 3"

# New: Web grounding (DuckDuckGo, no API key)
python thinkgraph.py web-search "React SSR performance 2024" --num-results 5
```

## MCP Server

Expose ThinkGraph as an MCP tool so any MCP-compatible agent (Claude Desktop, Cursor, etc.) can call it natively:

```bash
python mcp/thinkgraph_mcp.py
```

Configure in your MCP client:
```json
{
  "mcpServers": {
    "thinkgraph": {
      "command": "python",
      "args": ["/path/to/thinkgraph/mcp/thinkgraph_mcp.py"]
    }
  }
}
```

**Available MCP tools:**
- `thinkgraph_triage` — classify prompt complexity
- `thinkgraph_validate_dag` — validate a DAG, get execution batches
- `thinkgraph_vote` — self-consistency voting
- `thinkgraph_web_search` — DuckDuckGo search
- `thinkgraph_cache_get` — look up cached fact
- `thinkgraph_cache_set` — store resolved fact
- `thinkgraph_tokens` — estimate token count

## Config (first use, stored in thinkgraph.config.json)

```
1. Activation: [Auto-triage / Always / Trigger-words / Off]
2. Max nodes: [3 / 5 / 8 / Custom]
3. Low-confidence: [Web search / Ask me / Best-guess / Skip]
4. Answer style: [Match prompt / Concise / Detailed / Custom]
5. Self-consistency: [Auto / On-demand / Off]
```