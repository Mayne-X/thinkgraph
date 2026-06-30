# ThinkGraph — Prompt Templates

These are the verbatim prompts used at each stage. Copy-paste into the agent's context or inject via the CLI.

---

## Triage Prompt

```
Classify this user prompt into exactly ONE category:
- trivial: single factual lookup, no reasoning needed
- single-hop: one inference step, straightforward
- multi-hop: needs 2+ facts, some may depend on each other
- planning: open-ended, many paths, constraint-heavy
- creative: subjective, opinion-based, no factual grounding

Return ONLY the category name, nothing else.

User prompt: {prompt}
```

## Decompose Prompt

```
Break this complex question into atomic sub-questions that must be answered first.

RULES:
1. Each sub-question is ONE fact, not a compound question.
2. List dependencies: which sub-questions must be answered before others?
3. Max {max_nodes} sub-questions.
4. Max depth {max_depth} (no recursive sub-questions).
5. Use this exact JSON format:

{
  "nodes": [
    {"id": "Q1", "q": "first atomic question", "deps": []},
    {"id": "Q2", "q": "second atomic question", "deps": ["Q1"]}
  ]
}

User prompt: {prompt}

If this prompt is already atomic, return {"nodes": []}.
```

## Node Resolution Prompt

```
Answer this atomic sub-question precisely and factually.
Be concise: ≤150 tokens.

Return EXACTLY this JSON (no other text):
{"claim": "your factual answer", "confidence": 0.0-1.0, "source": "internal"}

Confidence guide:
- 0.9-1.0: certain, well-established fact
- 0.7-0.89: high confidence, minor uncertainty
- 0.5-0.69: moderate confidence, could be wrong
- below 0.5: low confidence, likely guessing

Sub-question: {question}

Context from previously resolved facts:
{parent_context}
```

## Synthesis Prompt

```
You are given verified sub-facts about a complex question.
Use ONLY these facts to answer the original prompt.
If the facts are insufficient, explicitly say what is missing.

VERIFIED FACTS:
{fact_sheet}

ORIGINAL QUESTION:
{user_prompt}

RULES:
- Base your answer STRICTLY on the verified facts above.
- If any fact has confidence < 0.8, note the uncertainty in your answer.
- If critical facts are missing, say "I cannot fully answer because: [gap]".
- Do NOT hallucinate additional facts beyond what is provided.
- Format your answer to match the user's expected style.
```

## Low-Confidence Follow-Up Prompt

```
I resolved a sub-question but with low confidence (0.XX).

Sub-question: {question}
My best attempt: {claim}

To improve accuracy, I need your help:

1. Do you know the answer to: {question}
2. Should I search the web for this fact?
3. Should I proceed with this best-guess and flag the uncertainty?

[Provide answer / Web search / Proceed with best-guess / Skip this fact]
```
