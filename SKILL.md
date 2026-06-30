---
name: thinkgraph
description: Use for any complex, multi-hop, or constraint-satisfaction question. Decomposes the prompt into a dependency DAG of atomic facts, resolves them sequentially, and synthesizes a grounded answer. Gives 50%+ accuracy boost on hard prompts while minimizing token waste. Trigger on: "multi-step", "compare X and Y", "plan", "analyze", "evaluate", "design", or any prompt needing multiple facts to answer correctly.
---

# thinkgraph — Pre-Computation Graph

You MUST follow this protocol for complex prompts. It forces structured thinking before answering, preventing hallucination and missed constraints.

## When to activate

**Always activate** for prompts that satisfy ANY of:
- Requires combining 2+ independent facts
- Involves constraint satisfaction or trade-offs
- Asks for a plan, analysis, evaluation, or comparison
- Has implicit dependencies between parts
- Could be wrong if any sub-fact is assumed instead of verified

**Skip entirely** for:
- Simple factual lookups ("what is X?")
- Single-hop questions with one answer
- Conversational/chitchat
- Explicit single-file edits or small code changes

When uncertain, ask the user: **"This looks complex enough for structured decomposition. Run ThinkGraph? [Yes, full pipeline / Yes, lite (max 3 nodes) / Skip — answer directly / Custom]"**

## Onboarding (first use per project)

On first invocation, run these 5 questions. Store answers in `thinkgraph.config.json` (gitignored).

```
1. When should ThinkGraph activate?
   [Auto-triage (smart detection) / Always-on / Trigger-words only / Off]

2. Max sub-questions (DAG nodes) per prompt?
   [3 / 5 / 8 / Custom number]

3. Low-confidence node handling?
   [Auto-web-search / Ask me each time / Best-guess and flag / Skip the node]

4. Default final answer style?
   [Match prompt style / Concise by default / Detailed by default / Custom]

5. Helper CLI mode?
   [Use if installed / Protocol-only (no CLI) / CLI required]
```

## Workflow

### Stage 1: Triage

Classify the prompt into one of:

| Class | Criteria | Action |
|---|---|---|
| **trivial** | Single fact, no reasoning | Answer directly, exit |
| **single-hop** | One inference step | Answer directly with brief reasoning |
| **multi-hop** | 2-3 facts needed, some dependent | Enter full pipeline |
| **planning** | Open-ended, many paths, constraint-heavy | Enter full pipeline |
| **creative** | Subjective, no factual grounding | Answer directly (graph adds nothing) |

If `thinkgraph CLI` is available and configured, run:
```bash
python thinkgraph.py triage "USER_PROMPT"
```
Otherwise, classify inline using the criteria above.

If borderline between single-hop and multi-hop, **ask the user** (see above).

### Stage 2: Decompose

Break the prompt into a DAG of atomic sub-questions.

**Output format** (JSON):
```json
{
  "nodes": [
    {"id": "Q1", "q": "atomic sub-question 1", "deps": []},
    {"id": "Q2", "q": "atomic sub-question 2", "deps": ["Q1"]},
    {"id": "Q3", "q": "atomic sub-question 3", "deps": []}
  ],
  "edges": [["Q1", "Q2"], ["Q3", "Q2"]]
}
```

**Constraints:**
- Each node is ONE atomic fact. Not "explain X and Y" — split into "what is X" and "what is Y".
- `deps` lists nodes that must resolve BEFORE this one (topological order).
- Max nodes = user's configured budget (default 5).
- Max depth = 2 (no recursive sub-sub-questions in v1).
- If zero sub-questions are needed (the prompt is already atomic), answer directly.
- Leaf nodes (no deps) can resolve in parallel. Dependent nodes resolve after their parents.

If `thinkgraph CLI` is available:
```bash
python thinkgraph.py decompose "USER_PROMPT" --max-nodes 5 --max-depth 2
```

**Show the user the proposed DAG** before resolving:

"Proposed decomposition (N sub-questions):
1. Q1: [text] (independent)
2. Q2: [text] (depends on Q1)
3. Q3: [text] (independent)

**[Approve all / Edit nodes / Regenerate / Add custom node / Remove a node]**"

Wait for user response before proceeding.

### Stage 3: Resolve

For each node, in topological order (parallelize independent nodes):

1. **Check cache first.** Normalize the question → hash → look up in cache. If hit and confidence ≥ 0.8, reuse.
2. **Resolve the node.** Send to LLM with this prompt:

```
Answer this atomic question in ≤150 tokens. Be precise and factual.
Return EXACTLY this JSON format:
{"claim": "your answer", "confidence": 0.0-1.0, "source": "internal|derived"}

Question: {node.q}

Context from parent answers: {parent_facts_if_any}
```

3. **If confidence < 0.6**, handle per user config:
   - Auto-web-search: do a web search for this specific fact
   - Ask me: present the sub-question to the user: "I'm uncertain about: [node.q]. What's the answer? [Provide answer / Skip / Use web search]"
   - Best-guess: proceed but mark fact as uncertain in synthesis
   - Skip: exclude this node and its dependents from synthesis

4. **Store in cache.** `thinkgraph cache-set <hash> <fact>` or write to `thinkgraph.cache.json`.

5. **Early termination check.** After each batch, check: can the main answer already be formed from resolved facts? If yes, skip remaining nodes.

**Token budget per node:** ≤300 tokens total (prompt + response). Hard cap.

### Stage 4: Synthesize

Build a condensed fact-sheet from resolved nodes, then answer the original prompt.

**Fact-sheet format** (one line per node):
```
Q1 → [claim] (conf: 0.95)
Q2 → [claim] (conf: 0.72, derived from Q1)
Q3 → [claim] (conf: 0.90)
```

**Synthesis prompt:**
```
You are given verified sub-facts about a complex question. Use ONLY these facts to answer the original prompt. If the facts are insufficient, explicitly say what's missing.

VERIFIED FACTS:
{fact_sheet}

ORIGINAL QUESTION:
{user_prompt}

INSTRUCTIONS:
- Base your answer strictly on the verified facts above.
- If any fact has confidence < 0.8, note the uncertainty.
- If critical facts are missing, say "I cannot fully answer because: [gap]".
- Format: match the user's expected output style (concise/detailed/code/etc).
- Do NOT hallucinate additional facts beyond what's provided.
```

**Budget check:** If total tokens used exceed 4× a typical direct answer, abort pipeline and answer directly instead. Tell the user: "Pipeline exceeded token budget — answering directly."

### Stage 5: Present Answer

- If all facts had confidence ≥ 0.8: present the answer directly.
- If any fact had confidence < 0.8: append an uncertainty note:
  "**Note:** Some parts of this answer are based on lower-confidence sub-facts (marked in the decomposition). Treat with appropriate caution."
- If any node was skipped: note which parts are missing.

## Token Budget Enforcement

| Stage | Max tokens (output) |
|---|---|
| Triage | 50 |
| Decompose | 200 |
| Per node (in+out) | 300 |
| Synthesize | 600 |
| **Hard ceiling** | **4× direct answer** |

If the ceiling is breached, abort to direct answer and notify user.

## DAG JSON Schema

Full schema for the decomposition output:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["nodes"],
  "properties": {
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "q", "deps"],
        "properties": {
          "id": { "type": "string", "pattern": "^Q[0-9]+$" },
          "q": { "type": "string", "minLength": 5, "maxLength": 200 },
          "deps": {
            "type": "array",
            "items": { "type": "string", "pattern": "^Q[0-9]+$" },
            "uniqueItems": true
          }
        }
      },
      "maxItems": 8
    }
  }
}
```

## CLI Integration

If the helper CLI is installed and configured (mode: "use-if-installed" or "required"), use these commands:

```bash
# Triage classification
python thinkgraph.py triage "prompt"

# Decompose into DAG
python thinkgraph.py decompose "prompt" --max-nodes 5 --max-depth 2

# Validate a DAG file
python thinkgraph.py validate-dag graph.json

# Cache operations
python thinkgraph.py cache-get <normalized_question>
python thinkgraph.py cache-set <normalized_question> "<claim>" <confidence>

# Token counting
python thinkgraph.py tokens "text to count"

# Aggregate facts into synthesis sheet
python thinkgraph.py aggregate facts.json
```

If the CLI is not installed, perform all operations inline using the pseudocode in `protocol/dag.md`.

## Edge Cases

- **Prompt is already atomic:** Triage as single-hop, answer directly. Do not decompose.
- **Circular dependencies detected:** Reject the DAG, regenerate with stricter deps.
- **All nodes resolve to same answer:** Still synthesize — the convergence itself is meaningful.
- **User rejects decomposition:** Fall back to direct answer. Respect the user's judgment.
- **Sub-question is opinion-based:** Mark confidence as 0.5 (inherently uncertain), note in synthesis.
- **Prompt contains "and" but facts are independent:** Split into separate parallel nodes, no deps between them.
