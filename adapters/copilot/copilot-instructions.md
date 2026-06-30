# thinkgraph — Structured Decomposition Protocol

Paste the following into your `.github/copilot-instructions.md` file.

---

For complex, multi-hop, or constraint-satisfaction prompts, decompose before answering.

**Skip** if: single factual lookup, single inference step, chitchat, small code edits.

**Protocol:**

1. **Triage** — Classify: trivial | single-hop | multi-hop | planning | creative
   - Trivial/single-hop/creative -> answer directly
   - Borderline -> ask: "Run ThinkGraph? [Yes / Skip]"

2. **Decompose** — Emit DAG: `{"nodes": [{"id": "Q1", "q": "atomic fact", "deps": []}]}`
   - Each node = ONE fact, max 5, depth <= 2
   - Auto-proceed (no approval needed)

3. **Resolve** — Topological order, check cache first, resolve each node:
   - `{"claim": "...", "confidence": 0.0-1.0}`
   - Low confidence (<0.6) -> ask user or skip
   - Cache results, early exit if answer emerges

4. **Synthesize** — Fact-sheet -> answer using ONLY verified facts:
   - `Q1 -> [fact] (conf: 0.95)`
   - Flag gaps and low-confidence items

5. **Present** — Answer with uncertainty notes if needed.

**Budgets:** Triage <=50 tok, Decompose <=200 tok, Per node <=300 tok, Synthesize <=600 tok, Ceiling = 4x direct cost.
