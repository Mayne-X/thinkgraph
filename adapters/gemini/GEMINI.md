# thinkgraph — Pre-Computation Graph

Paste the following into your `GEMINI.md` file.

---

## Structured Decomposition Protocol (thinkgraph)

For complex, multi-hop, or constraint-satisfaction prompts, follow this protocol before answering.

### Trigger conditions

Activate when the prompt:
- Requires combining 2+ independent facts
- Involves constraint satisfaction or trade-offs
- Asks for a plan, analysis, evaluation, or comparison

Skip for: simple lookups, single-hop questions, chitchat, small code changes.

### Protocol (5 stages)

**1. Triage** — Classify prompt complexity:
- trivial/single-hop → answer directly
- multi-hop/planning → enter decomposition pipeline

**2. Decompose** — Break into atomic sub-questions (DAG):
```json
{"nodes": [{"id": "Q1", "q": "one atomic fact", "deps": []}]}
```
- Max 5 nodes, max depth 2
- Each node = ONE fact, not compound
- Show proposed decomposition, wait for user approval

**3. Resolve** — Answer each node in dependency order:
- Leaf nodes (no deps) resolve first, can be parallelized
- Each answer: `{"claim": "...", "confidence": 0.0-1.0}`
- Low confidence (<0.6) → ask user or skip
- Cache results for reuse

**4. Synthesize** — Build fact-sheet, answer original prompt using ONLY verified facts:
```
Q1 → [fact] (conf: 0.95)
Q2 → [fact] (conf: 0.72)
```
Flag gaps and low-confidence items.

**5. Present** — Deliver answer with uncertainty notes if applicable.

### Token budgets

- Triage: ≤50 tokens
- Decompose: ≤200 tokens
- Per node: ≤300 tokens (in+out)
- Synthesize: ≤600 tokens
- Hard ceiling: 4× direct answer (abort to direct if exceeded)
