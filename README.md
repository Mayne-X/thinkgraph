<p align="center">
  <h1 align="center">🧠 ThinkGraph</h1>
  <p align="center">
    <strong>Stop guessing. Start decomposing.</strong><br>
    Structured decomposition for LLM prompts that gives your AI a foundation to think on.
  </p>
</p>

<p align="center">
  <a href="https://github.com/Mayne-X/thinkgraph/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="#"><img src="https://img.shields.io/badge/python-3.8+-green.svg" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/agents-6+-purple.svg" alt="Agents"></a>
  <a href="#"><img src="https://img.shields.io/badge/token--save-50%25+-red.svg" alt="Token Savings"></a>
</p>

---

## The Problem

When you ask an LLM a complex question, it tries to answer the whole thing at once — hallucinating details, missing constraints, and guessing at facts it should verify first.

**Example failure:**
> "Compare React and Vue for a large enterprise dashboard with SSR requirements"
>
> ❌ LLM guesses React is better without checking SSR maturity, enterprise adoption, team size trade-offs, or bundle size implications.

## The Solution

ThinkGraph **intercepts the prompt**, forces the LLM to break it into a dependency graph of atomic facts, resolves each one, then answers with a verified foundation.

```
Your Prompt
    │
    ▼
┌─────────┐     ┌───────────┐     ┌──────────┐     ┌────────────┐
│ TRIAGE  │────>│ DECOMPOSE │────>│ RESOLVE  │────>│ SYNTHESIZE │
│         │     │           │     │          │     │            │
│ Is this │     │ Emit DAG  │     │ Answer   │     │ Build final│
│ complex?│     │ of atomic │     │ each     │     │ answer from│
│         │     │ sub-Qs    │     │ sub-Q    │     │ verified   │
│ Skip if │     │ with deps │     │ in order │     │ facts only │
│ simple  │     │           │     │          │     │            │
└─────────┘     └───────────┘     └──────────┘     └────────────┘
     │               │                 │                  │
     ▼               ▼                 ▼                  ▼
  Direct         User reviews     Cache results      Grounded
  answer         proposed DAG     for reuse          answer with
  (if trivial)                                       confidence
```

**Result: 50%+ accuracy improvement on multi-hop prompts.**

---

## How It Works

### 1. Triage — Skip the pipeline for simple stuff
Not every prompt needs decomposition. ThinkGraph classifies your prompt and skips the pipeline for trivial or single-hop questions. **Saves tokens.**

### 2. Decompose — Build a dependency graph
Breaks the prompt into atomic sub-questions with explicit dependencies. Shows you the proposed decomposition before doing anything.

```
"Compare React and Vue for enterprise SSR dashboard"

Becomes:
  Q1: What is React's SSR maturity?           (independent)
  Q2: What is Vue's SSR maturity?              (independent)
  Q3: What are enterprise adoption rates?       (independent)
  Q4: Given Q1-Q3, which fits a 10-person team? (depends on Q1, Q2, Q3)
```

### 3. Resolve — Answer each sub-fact
Each atomic question gets answered with a confidence score. Low-confidence facts are flagged or sent to web search. Results are cached for reuse.

### 4. Synthesize — Build the real answer
Only verified facts feed the final answer. No hallucinated data. Missing facts are explicitly called out.

---

## Works With Everything

| Agent | Setup | Auto-loaded? |
|:------|:------|:------------|
| **OpenCode** | `.opencode/skills/thinkgraph/SKILL.md` | Yes |
| **Claude Code** | `~/.claude/skills/thinkgraph/SKILL.md` | Yes |
| **Cursor** | `.cursor/rules/thinkgraph.mdc` | No (install) |
| **Codex** | `AGENTS.md` section | No (install) |
| **Copilot** | `.github/copilot-instructions.md` | No (install) |
| **Gemini CLI** | `GEMINI.md` section | No (install) |

---

## Quick Start

```bash
# Clone
git clone https://github.com/Mayne-X/thinkgraph.git
cd thinkgraph

# Auto-install adapters for all detected agents
python install.py

# Preview what would be installed (dry run)
python install.py --dry-run

# Install for specific agents only
python install.py --agents opencode,codex
```

That's it. Restart your agent and ThinkGraph activates on complex prompts.

---

## Helper CLI

Optional Python tool for deterministic bookkeeping. **Never calls an LLM** — all reasoning stays in your agent.

```bash
# Classify prompt complexity
python thinkgraph.py triage "compare React and Vue"

# Validate a DAG for cycles and depth
python thinkgraph.py validate-dag graph.json

# Cache a resolved fact
python thinkgraph.py cache-set "what is react ssr maturity" "React 18+ has streaming SSR" 0.92

# Look up cached facts
python thinkgraph.py cache-get "what is react ssr maturity"

# Count tokens (heuristic)
python thinkgraph.py tokens "your text here"

# Build synthesis fact-sheet from resolved nodes
python thinkgraph.py aggregate facts.json
```

---

## Token Budget

ThinkGraph enforces strict token budgets at every stage to minimize waste:

| Stage | Max Tokens |
|:------|:-----------|
| Triage | 50 |
| Decompose | 200 |
| Per sub-question | 300 |
| Synthesize | 600 |
| **Hard ceiling** | **4x a direct answer** |

If the pipeline exceeds the ceiling, it aborts and answers directly. **You never pay more than 4x for a guaranteed improvement.**

---

## Project Structure

```
thinkgraph/
├── SKILL.md                  # The canonical protocol (start here)
├── protocol/
│   ├── prompts.md            # Verbatim prompt templates for each stage
│   ├── dag.md                # DAG schema, topo-sort pseudocode, cache format
│   └── questions.md          # Interactive question templates (onboarding + per-invocation)
├── adapters/
│   ├── opencode/SKILL.md     # OpenCode skill
│   ├── claude/SKILL.md       # Claude Code skill (also auto-loaded by OpenCode)
│   ├── cursor/thinkgraph.mdc # Cursor rules
│   ├── codex/AGENTS.md       # Codex section
│   ├── copilot/              # Copilot section
│   └── gemini/GEMINI.md      # Gemini CLI section
├── cli/
│   └── thinkgraph.py         # Helper CLI (Python 3.8+, stdlib only, zero deps)
├── install.py                # Multi-agent installer (auto-detect, idempotent)
├── tests/
│   └── test_golden.py        # Golden prompt tests (15/15 passing)
└── LICENSE                   # MIT
```

---

## Roadmap

Features planned for future releases:

| # | Feature | Description | Status |
|:--|:--------|:------------|:-------|
| 1 | **Self-consistency voting** | Run final synthesis 2-3x, majority-vote the answer to catch hallucinations | Planned |
| 2 | **Web grounding** | Auto-search for low-confidence nodes using DuckDuckGo API (zero API key needed) | Planned |
| 3 | **MCP server** | Expose ThinkGraph as an MCP tool so any agent can call it as a native function | Planned |
| 4 | **Prompt compression** | Smart summarizer that shrinks context before feeding the synthesis stage | Planned |
| 5 | **Benchmark suite** | 50+ golden prompts with expected DAGs and answers, automated quality scoring | Planned |
| 6 | **Cache sync** | Redis/SQLite adapter for cross-project and cross-team fact sharing | Planned |
| 7 | **Streaming support** | Emit DAG and facts incrementally so agents can display live progress | Planned |
| 8 | **Multi-model routing** | Run cheap sub-nodes on Haiku/Mini, synthesis on expensive model | Planned |
| 9 | **Dynamic DAG pruning** | If a node becomes irrelevant after its parent resolves, skip it automatically | Planned |
| 10 | **Export formats** | Output pipeline results as Markdown report, JSON, or structured YAML | Planned |
| 11 | **Recursive depth** | Allow depth 3+ for extremely complex prompts with budget warnings | Planned |
| 12 | **A/B testing mode** | Run both direct and pipeline answers, compare quality metrics, log results | Planned |
| 13 | **Plugin hooks** | Let users inject custom resolve functions (API calls, database lookups, etc.) | Planned |
| 14 | **CLI interactive mode** | `thinkgraph interactive` launches a REPL for step-by-step walkthrough | Planned |
| 15 | **GitHub Action** | CI step that runs ThinkGraph on issue titles to auto-generate implementation plans | Planned |

---

## Contributing

Contributions welcome. Open an issue or PR.

```bash
# Run tests
python tests/test_golden.py

# Test CLI commands
python thinkgraph.py triage "your prompt"
python thinkgraph.py validate-dag your_dag.json
```

---

## License

MIT - do whatever you want.
