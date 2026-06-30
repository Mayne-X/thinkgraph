---
name: thinkgraph
description: Use for complex, multi-hop, or constraint-satisfaction questions. Decomposes into a DAG of atomic facts, resolves them, synthesizes a grounded answer. Skip for trivial lookups, chitchat, or small code edits. Trigger on: compare, plan, analyze, evaluate, design, trade-off, or any prompt needing 2+ facts.
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
3. If confidence < 0.6: ask user or skip
4. Cache result
5. Early exit if answer already emerges from resolved facts

Budget: ≤300 tokens per node (in+out).

### 4. Synthesize

Build fact-sheet (one line per node), then answer using ONLY verified facts:
```
Q1 → [fact] (conf: 0.95)
Q2 → [fact] (conf: 0.72, derived from Q1)
```

- Flag gaps and low-confidence items
- If budget exceeds 4× estimated direct cost, abort to direct answer

### 5. Present

- High confidence (all ≥ 0.8): answer directly
- Low confidence present: append uncertainty note
- Skipped nodes: note missing parts

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
python thinkgraph.py triage "prompt"
python thinkgraph.py validate-dag graph.json
python thinkgraph.py cache-get "question"
python thinkgraph.py tokens "text"
python thinkgraph.py aggregate facts.json
```

## Config (first use, stored in thinkgraph.config.json)

```
1. Activation: [Auto-triage / Always / Trigger-words / Off]
2. Max nodes: [3 / 5 / 8 / Custom]
3. Low-confidence: [Web search / Ask me / Best-guess / Skip]
4. Answer style: [Match prompt / Concise / Detailed / Custom]
```
