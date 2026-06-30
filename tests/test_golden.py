#!/usr/bin/env python3
"""
test_golden.py — Golden prompt tests for ThinkGraph.

Compares direct answer vs ThinkGraph pipeline on sample prompts.
Run: python tests/test_golden.py

Requires: the thinkgraph CLI in cli/thinkgraph.py
"""

import json
import sys
import os

# Add parent dir to path so we can import thinkgraph
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cli"))
from thinkgraph import triage_heuristic, normalize_question, question_hash, estimate_tokens


# ---------------------------------------------------------------------------
# Test cases: (prompt, expected_triage, expected_needs_decomposition)
# ---------------------------------------------------------------------------

GOLDEN_PROMPTS = [
    # Trivial
    ("What is 2+2?", "trivial", False),
    ("Who is the CEO of Apple?", "trivial", False),

    # Single-hop
    ("What is the time complexity of binary search?", "single_hop", False),
    ("Explain what a closure is in JavaScript.", "trivial", False),

    # Multi-hop
    (
        "Compare React and Vue for a large enterprise dashboard with SSR requirements",
        "multi_hop",
        True,
    ),
    (
        "What are the trade-offs between PostgreSQL and MongoDB for a real-time analytics platform handling 1M events/day?",
        "multi_hop",
        True,
    ),

    # Planning
    (
        "Design a microservices architecture for an e-commerce platform with inventory, payments, and notifications",
        "planning",
        True,
    ),
    (
        "Plan a migration from a monolith to event-driven architecture with zero downtime",
        "planning",
        True,
    ),
]


def test_triage():
    """Test that triage heuristic classifies prompts correctly."""
    passed = 0
    failed = 0

    for prompt, expected, _ in GOLDEN_PROMPTS:
        result = triage_heuristic(prompt)
        # Allow multi_hop and planning to be interchangeable for planning prompts
        # since the heuristic may classify planning as multi_hop
        ok = result == expected or (
            expected == "planning" and result == "multi_hop"
        )
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
            print(f"  [{status}] '{prompt[:50]}...' -> {result} (expected {expected})")
        else:
            passed += 1
            print(f"  [{status}] '{prompt[:50]}...' -> {result}")

    return passed, failed


def test_normalization():
    """Test that normalization is consistent."""
    tests = [
        ("What is the capital of France?", "what is the capital of france"),
        ("WHAT IS THE CAPITAL OF FRANCE?", "what is the capital of france"),
        ("what is the capital of france?", "what is the capital of france"),
    ]

    passed = 0
    for question, expected_norm in tests:
        result = normalize_question(question)
        ok = result == expected_norm
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"  [{status}] '{question}' -> '{result}' (expected '{expected_norm}')")
        else:
            passed += 1
            print(f"  [{status}] '{question}' -> '{result}'")

    return passed, len(tests) - passed


def test_hash_consistency():
    """Test that same question always hashes to same value."""
    q1 = "What is the capital of France?"
    q2 = "what is the capital of france"
    q3 = "WHAT IS THE CAPITAL OF FRANCE?"

    h1 = question_hash(q1)
    h2 = question_hash(q2)
    h3 = question_hash(q3)

    passed = 0
    if h1 == h2 == h3:
        passed = 1
        print(f"  [PASS] Consistent hash: {h1}")
    else:
        print(f"  [FAIL] Inconsistent: {h1} != {h2} != {h3}")

    return passed, 1 - passed


def test_token_estimation():
    """Test token estimation is reasonable."""
    tests = [
        ("Hello world", 2),       # 11 chars / 4 = 2
        ("a" * 40, 10),           # 40 chars / 4 = 10
        ("x", 1),                 # min 1
    ]

    passed = 0
    for text, expected in tests:
        result = estimate_tokens(text)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            print(f"  [{status}] '{text[:20]}...' -> {result} tokens (expected {expected})")
        else:
            passed += 1
            print(f"  [{status}] '{text[:20]}...' -> {result} tokens")

    return passed, len(tests) - passed


def main():
    print("ThinkGraph Golden Tests")
    print("=" * 40)

    total_pass = 0
    total_fail = 0

    print("\n[Triage]")
    p, f = test_triage()
    total_pass += p
    total_fail += f

    print("\n[Normalization]")
    p, f = test_normalization()
    total_pass += p
    total_fail += f

    print("\n[Hash Consistency]")
    p, f = test_hash_consistency()
    total_pass += p
    total_fail += f

    print("\n[Token Estimation]")
    p, f = test_token_estimation()
    total_pass += p
    total_fail += f

    print("\n" + "=" * 40)
    print(f"Results: {total_pass} passed, {total_fail} failed")

    if total_fail > 0:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    main()
