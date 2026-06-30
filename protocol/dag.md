# ThinkGraph — DAG Execution Reference

## Topological Sort (inline pseudocode)

When the CLI is not available, use this algorithm to determine execution order:

```
function topoSort(nodes, edges):
  inDegree = {node.id: 0 for node in nodes}
  for each [from, to] in edges:
    inDegree[to]++

  queue = [node.id for node in nodes if inDegree[node.id] == 0]
  order = []
  batches = []

  while queue is not empty:
    batch = copy(queue)
    batches.append(batch)
    queue = []
    for each id in batch:
      order.append(id)
      for each [from, to] in edges where from == id:
        inDegree[to]--
        if inDegree[to] == 0:
          queue.append(to)

  if len(order) != len(nodes):
    ERROR: cycle detected

  return batches  // each batch runs in parallel
```

## Cycle Detection

After emitting the DAG, verify:
1. Run topoSort. If `len(order) != len(nodes)`, a cycle exists.
2. Re-emit the DAG with strict dependency constraints. Maximum 1 retry.
3. If still cyclic on second attempt, report to user and fall back to direct answer.

## Depth Check

Depth = longest path from any root (deps=[]) to any leaf.

```
function depth(nodeId, memo={}):
  if nodeId in memo: return memo[nodeId]
  node = nodes[nodeId]
  if node.deps is empty: return 0
  memo[nodeId] = 1 + max(depth(dep) for dep in node.deps)
  return memo[nodeId]
```

Max depth = user config (default 2). If exceeded, flatten: split deep chains into parallel nodes where possible.

## Parallel Execution Batches

The `batches` array from topoSort gives you the execution schedule:

```
Batch 0: [Q1, Q3]  (no deps, run in parallel)
Batch 1: [Q2]      (depends on Q1, wait for batch 0)
Batch 2: [Q4]      (depends on Q2 and Q3, wait for batch 1)
```

Within each batch, all nodes can resolve simultaneously (agent can use sub-agents or sequential with no dependency risk).

## Normalized Question Hash

For cache deduplication, normalize questions before hashing:

```
function normalize(question):
  q = question.lower()
  q = strip punctuation (keep alphanumeric and spaces)
  q = collapse multiple spaces to one
  q = strip leading/trailing whitespace
  q = sort words alphabetically (for reorder-insensitive matching)
  return sha256(q)[:16]
```

This ensures "What is X?" and "what is x?" and "X is what?" all map to the same cache key.

## Cache Schema

`thinkgraph.cache.json` (per-project, gitignored):

```json
{
  "version": 1,
  "entries": {
    "<hash>": {
      "question": "normalized question text",
      "claim": "the factual answer",
      "confidence": 0.95,
      "source": "internal|derived",
      "resolved_at": "2026-06-30T12:00:00Z",
      "ttl_days": 30
    }
  }
}
```

## Token Counting (heuristic)

When the CLI is not available, estimate tokens as:

```
tokens ≈ len(text) / 4
```

This is approximate. For precise counting, use `thinkgraph.py tokens "text"`.

## Confidence-Weighted Fact Sheet

When building the synthesis fact-sheet, order nodes by confidence (highest first):

```
Q1 → [claim] (conf: 0.95)
Q3 → [claim] (conf: 0.90)
Q2 → [claim] (conf: 0.72, derived from Q1)
```

This helps the synthesis prompt prioritize reliable facts.
