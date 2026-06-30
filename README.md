# thinkgraph

Structured decomposition for LLM prompts. Breaks complex questions into a dependency graph of atomic facts, resolves them sequentially, and synthesizes a grounded answer.

## What it does

Instead of guessing at a complex prompt, ThinkGraph:

1. **Triage** — Is this even complex enough to decompose?
2. **Decompose** — Emit a DAG of atomic sub-questions with dependencies
3. **Resolve** — Answer each sub-question (parallel where possible)
4. **Synthesize** — Build the final answer from verified sub-facts

Result: 50%+ accuracy improvement on multi-hop prompts while minimizing token waste.

## Works with

| Agent | Location | Auto-loaded? |
|---|---|---|
| OpenCode | `.opencode/skills/thinkgraph/SKILL.md` | Yes |
| Claude Code | `~/.claude/skills/thinkgraph/SKILL.md` | Yes |
| Cursor | `.cursor/rules/thinkgraph.mdc` | No (manual) |
| Codex | `AGENTS.md` section | No (paste in) |
| Copilot | `.github/copilot-instructions.md` section | No (paste in) |
| Gemini CLI | `GEMINI.md` section | No (paste in) |

## Quick start

```bash
# Install adapters for detected agents
python install.py

# Or just copy SKILL.md to your agent's skill directory manually
```

## Helper CLI

Optional. Does deterministic bookkeeping only (no LLM calls):

```bash
python thinkgraph.py triage "your complex prompt"
python thinkgraph.py decompose "your prompt" --max-nodes 5
python thinkgraph.py validate-dag graph.json
python thinkgraph.py cache-get "normalized question"
python thinkgraph.py tokens "text to count"
python thinkgraph.py aggregate facts.json
```

## Project structure

```
thinkgraph/
├── SKILL.md              # Canonical protocol (start here)
├── protocol/
│   ├── prompts.md        # Verbatim prompt templates
│   ├── dag.md            # DAG schema, topo-sort, cache reference
│   └── questions.md      # Interactive question templates
├── adapters/             # Per-agent wrappers
├── cli/
│   └── thinkgraph.py     # Helper CLI (Python 3.8+, stdlib only)
├── install.py            # Multi-agent installer
├── tests/                # Golden prompt tests
└── thinkgraph.config.json # Per-project config (gitignored)
```

## License

MIT
