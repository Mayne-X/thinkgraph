# thinkgraph — Pre-Computation Graph

Paste the following into your `GEMINI.md` file.

---

## Structured Decomposition Protocol (thinkgraph) v1.1

For complex, multi-hop, or constraint-satisfaction prompts. Includes self-consistency voting, web grounding, and MCP server support.

### Trigger conditions

Activate when the prompt:
- Requires combining 2+ independent facts
- Involves constraint satisfaction or trade-offs
- Asks for a plan, analysis, evaluation, or comparison

Skip for: simple lookups, single-hop questions, chitchat, small code changes.

### Protocol (6 stages)

**1. Triage** — Classify: trivial | single-hop | multi-hop | planning | creative

**2. Decompose** — Break into atomic sub-questions (DAG):
```json
{"nodes": [{"id": "Q1", "q": "one atomic fact", "deps": []}]}
```
Max 5 nodes, max depth 2.

**3. Resolve** — Answer each node in dependency order:
- Check cache first
- Return: `{"claim": "...", "confidence": 0.0-1.0}`
- If confidence < 0.6 → use web search: `thinkgraph.py web-search "query"`

**4. Self-Consistency Voting** — On high-stakes final answers:
```bash
thinkgraph.py vote "answer v1" "answer v2" "answer v3"
```
Jaccard centroid = most self-consistent response.

**5. Synthesize** — Fact-sheet then answer using ONLY verified facts. Flag gaps.

**6. Present** — Deliver with uncertainty notes and self-consistency note if applicable.

### Token budgets

- Triage: ≤50 | Decompose: ≤200 | Per node: ≤300 | Synthesize: ≤600
- Hard ceiling: 4× direct answer (abort to direct if exceeded)

### CLI

```bash
python thinkgraph.py triage "prompt"
python thinkgraph.py validate-dag graph.json
python thinkgraph.py vote "r1" "r2" "r3"
python thinkgraph.py web-search "query"
python thinkgraph.py cache-get "question"
python thinkgraph.py tokens "text"
```

### MCP server

```bash
python mcp/thinkgraph_mcp.py
```

7 tools: triage, validate-dag, vote, web-search, cache-get, cache-set, tokens