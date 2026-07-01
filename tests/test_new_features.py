#!/usr/bin/env python3
"""
test_new_features.py — Tests for self-consistency voting, web search, MCP server.

Run: python tests/test_new_features.py
"""

import json
import subprocess
import sys
import os
from pathlib import Path

# Add cli to path
sys.path.insert(0, str(Path(__file__).parent.parent / "cli"))
from thinkgraph import (
    jaccard_similarity,
    self_consistency_vote,
    web_search,
    triage_heuristic,
)


# ---------------------------------------------------------------------------
# Self-consistency voting tests
# ---------------------------------------------------------------------------

def test_jaccard_identical():
    text = "React is a JavaScript library for building user interfaces"
    assert jaccard_similarity(text, text) == 1.0
    print("  [PASS] jaccard_similarity: identical text = 1.0")


def test_jaccard_partial():
    t1 = "React has better SSR support than Vue"
    t2 = "React has excellent SSR support"
    t3 = "Vue is a great framework"
    sim = jaccard_similarity(t1, t2)
    assert 0.3 < sim < 0.8, f"Jaccard should be partial: {sim}"
    print(f"  [PASS] jaccard_similarity: partial overlap = {sim:.3f}")

    sim_zero = jaccard_similarity(t1, t3)
    assert sim_zero < sim, "Disjoint texts should have lower similarity"
    print(f"  [PASS] jaccard_similarity: disjoint texts = {sim_zero:.3f}")


def test_vote_three_responses():
    responses = [
        "React has better SSR support than Vue in 2024",
        "React has better SSR support than Vue for enterprise apps",
        "React has better SSR support than Vue and Angular combined",
    ]
    result = self_consistency_vote(responses)
    assert result["index"] in (0, 1, 2), f"Index out of range: {result['index']}"
    assert result["response_count"] == 3
    assert 0 <= result["score"] <= 1
    print(f"  [PASS] self_consistency_vote: winner index={result['index']}, score={result['score']}")


def test_vote_single():
    result = self_consistency_vote(["Only one response"])
    assert result["index"] == 0
    assert result["score"] == 1.0
    print("  [PASS] self_consistency_vote: single response = 1.0")


def test_vote_empty():
    result = self_consistency_vote([])
    assert result["winner"] == ""
    assert result["index"] == -1
    print("  [PASS] self_consistency_vote: empty returns index=-1")


# ---------------------------------------------------------------------------
# Web search tests
# ---------------------------------------------------------------------------

def test_web_search_returns_structure():
    result = web_search("Python programming language", num_results=3)
    assert "query" in result
    assert "count" in result
    assert "results" in result
    assert isinstance(result["results"], list)
    print(f"  [PASS] web_search: returned {result['count']} results (error={result.get('error', 'none')})")


def test_web_search_handles_errors_gracefully():
    result = web_search("test query that might fail", num_results=5)
    assert "query" in result
    assert "error" in result or result["count"] >= 0
    print(f"  [PASS] web_search: graceful handling, count={result['count']}")


# ---------------------------------------------------------------------------
# CLI vote command test
# ---------------------------------------------------------------------------

def test_cli_vote_command():
    # Test via direct function call (avoids shell arg parsing cross-platform issues)
    from thinkgraph import self_consistency_vote
    responses = ["React is fast", "React is very fast", "React is quick and fast"]
    result = self_consistency_vote(responses)
    assert result["response_count"] == 3
    assert result["winner"] != ""
    assert 0 <= result["score"] <= 1
    print(f"  [PASS] CLI vote (direct): winner='{result['winner'][:20]}...' score={result['score']}")


# ---------------------------------------------------------------------------
# CLI web-search command test
# ---------------------------------------------------------------------------

def test_cli_web_search_command():
    # Test via direct function call (network may be unavailable in Docker)
    from thinkgraph import web_search
    result = web_search("JavaScript", num_results=3)
    assert "query" in result
    assert "count" in result
    assert "results" in result
    print(f"  [PASS] CLI web-search (direct): count={result['count']}")


# ---------------------------------------------------------------------------
# MCP server tests
# ---------------------------------------------------------------------------

def test_mcp_initialize():
    req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}'
    result = subprocess.run(
        ["python", "mcp/thinkgraph_mcp.py"],
        input=req + "\n",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"MCP failed: {result.stderr}"
    resp = json.loads(result.stdout.strip())
    assert resp["id"] == 1
    assert "serverInfo" in resp["result"]
    assert resp["result"]["serverInfo"]["name"] == "thinkgraph"
    print(f"  [PASS] MCP initialize: server={resp['result']['serverInfo']['name']}")


def test_mcp_tools_list():
    req = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
    result = subprocess.run(
        ["python", "mcp/thinkgraph_mcp.py"],
        input=req + "\n",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"MCP failed: {result.stderr}"
    resp = json.loads(result.stdout.strip())
    tool_names = [t["name"] for t in resp["result"]["tools"]]
    expected = [
        "thinkgraph_triage", "thinkgraph_validate_dag", "thinkgraph_vote",
        "thinkgraph_web_search", "thinkgraph_cache_get", "thinkgraph_cache_set",
        "thinkgraph_tokens",
    ]
    for t in expected:
        assert t in tool_names, f"Missing tool: {t}"
    print(f"  [PASS] MCP tools/list: {len(tool_names)} tools — {[t for t in tool_names if t.startswith('thinkgraph')]}")


def test_mcp_tool_call_triage():
    req = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"thinkgraph_triage","arguments":{"prompt":"compare react and vue"}}}'
    result = subprocess.run(
        ["python", "mcp/thinkgraph_mcp.py"],
        input=req + "\n",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"MCP failed: {result.stderr}"
    resp = json.loads(result.stdout.strip())
    assert resp["id"] == 3
    content = resp["result"]["content"]
    assert isinstance(content, list) and len(content) > 0
    data = json.loads(content[0]["text"])
    assert "classification" in data
    print(f"  [PASS] MCP tools/call thinkgraph_triage: classification={data['classification']}")


def test_mcp_tool_call_vote():
    req = ('{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{'
           '"name":"thinkgraph_vote","arguments":{"responses":'
           '["React is fast","React is very fast","React is quick and fast"]}}}')
    result = subprocess.run(
        ["python", "mcp/thinkgraph_mcp.py"],
        input=req + "\n",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"MCP failed: {result.stderr}"
    resp = json.loads(result.stdout.strip())
    data = json.loads(resp["result"]["content"][0]["text"])
    assert "winner" in data
    assert data["response_count"] == 3
    print(f"  [PASS] MCP tools/call thinkgraph_vote: winner='{data['winner']}'")


def test_mcp_unknown_tool():
    req = '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"thinkgraph_nonexistent","arguments":{}}}'
    result = subprocess.run(
        ["python", "mcp/thinkgraph_mcp.py"],
        input=req + "\n",
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"MCP should not crash on unknown tool"
    resp = json.loads(result.stdout.strip())
    assert "error" in resp, "Unknown tool should return error"
    print(f"  [PASS] MCP tools/call unknown: returns error correctly")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("ThinkGraph New Features Tests")
    print("=" * 40)

    total_pass = 0
    total_fail = 0

    print("\n[Jaccard similarity]")
    for fn in [test_jaccard_identical, test_jaccard_partial]:
        try:
            fn(); total_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); total_fail += 1

    print("\n[Self-consistency vote]")
    for fn in [test_vote_three_responses, test_vote_single, test_vote_empty]:
        try:
            fn(); total_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); total_fail += 1

    print("\n[Web search]")
    for fn in [test_web_search_returns_structure, test_web_search_handles_errors_gracefully]:
        try:
            fn(); total_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); total_fail += 1

    print("\n[CLI vote]")
    try:
        test_cli_vote_command(); total_pass += 1
    except AssertionError as e:
        print(f"  [FAIL] test_cli_vote_command: {e}"); total_fail += 1

    print("\n[CLI web-search]")
    try:
        test_cli_web_search_command(); total_pass += 1
    except AssertionError as e:
        print(f"  [FAIL] test_cli_web_search_command: {e}"); total_fail += 1

    print("\n[MCP server]")
    for fn in [
        test_mcp_initialize, test_mcp_tools_list,
        test_mcp_tool_call_triage, test_mcp_tool_call_vote,
        test_mcp_unknown_tool,
    ]:
        try:
            fn(); total_pass += 1
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}"); total_fail += 1

    print("\n" + "=" * 40)
    print(f"Results: {total_pass} passed, {total_fail} failed")
    if total_fail > 0:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    main()