# ThinkGraph — Question Templates

## Onboarding Questions (first use per project)

These are asked once. Answers stored in `thinkgraph.config.json`.

### Q1: Activation Mode
```
When should ThinkGraph activate?

1. Auto-triage (smart detection) — I decide when decomposition helps
2. Always-on — every prompt goes through the full pipeline
3. Trigger-words only — only when you say "thinkgraph", "decompose", "analyze"
4. Off — disabled, answer directly

[Auto-triage / Always-on / Trigger-words / Off / Custom]
```

### Q2: Max Sub-Questions
```
Maximum sub-questions (DAG nodes) per prompt?

More nodes = more thorough but more tokens. Most prompts need 2-4.

[3 / 5 / 8 / Custom number]
```

### Q3: Low-Confidence Handling
```
When a sub-question resolves with low confidence (<0.6), what should I do?

1. Auto-web-search — search for the fact automatically
2. Ask me each time — present the uncertain sub-question to you
3. Best-guess and flag — proceed but mark uncertainty in final answer
4. Skip the node — exclude it and its dependents

[Web search / Ask me / Best-guess / Skip / Custom]
```

### Q4: Answer Style
```
Default final answer style?

1. Match prompt — mirror the user's tone and format
2. Concise — short, direct, no fluff (default)
3. Detailed — thorough explanation with examples
4. Custom format

[Match prompt / Concise / Detailed / Custom]
```

### Q5: CLI Mode
```
How should I handle the helper CLI?

1. Use if installed — optional, fall back to inline protocol
2. Protocol-only — never use CLI, always inline
3. CLI required — error if CLI not found (for power users)

[Use-if-installed / Protocol-only / Required / Custom]
```

---

## Per-Invocation Decision Points

### Triage Boundary (when classification is borderline)
```
This prompt could go either way:

- Direct answer (single-hop): {brief reason}
- Full pipeline (multi-hop): {brief reason}

Run ThinkGraph?

[Yes, full pipeline / Yes, lite (max 3 nodes) / Skip — answer directly / Custom]
```

### Decomposition Review (after Stage 2)
```
Proposed decomposition ({N} sub-questions):

1. Q1: {text} (independent)
2. Q2: {text} (depends on Q1)
3. Q3: {text} (independent)

Review options:

[Approve all / Edit nodes / Regenerate / Add custom node / Remove a node]
```

### Low-Confidence Node (Stage 3, confidence < 0.6)
```
Sub-question resolved with low confidence:

Q2: {question}
Best attempt: {claim}
Confidence: {confidence}

How should I handle this?

[Web search for this fact / I'll provide the answer / Proceed with best-guess / Skip this fact / Custom]
```

### Budget Threshold (80% of token ceiling)
```
Token budget at {percentage}% ({used}/{max}).

Options:

[Continue — use remaining budget / Finalize now with current facts / Switch to direct answer / Custom]
```

### Pipeline Aborted (budget exceeded)
```
Pipeline exceeded token budget ({used}/{max} tokens).
Falling back to direct answer.

[Proceed with direct answer / Cancel / Custom]
```
