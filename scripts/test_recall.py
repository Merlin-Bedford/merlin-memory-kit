#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MERLIN MEMORY KIT - test_recall.py
Health check: are the services up, is the collection non-empty, does recall
actually return sensible hits? Run this after every reboot and after every
index rebuild. Silent recall death is the failure mode this exists to kill.

Usage: python test_recall.py ["query one" "query two" ...]
By Merlin the Owl - MIT licensed.
"""
import json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load
from recall import embed, search

CFG = load()
QDRANT, OLLAMA, COLL = CFG["qdrant_url"], CFG["ollama_url"], CFG["collection"]

DEFAULT_TESTS = [
    "what are my core rules?",
    "what did I decide recently and why?",
    "where are my backups and how do I restore?",
    "what tasks am I in the middle of?",
]


def health():
    ok = True
    try:
        urllib.request.urlopen(OLLAMA + "/api/version", timeout=5).read()
        print("OK   embeddings server reachable", OLLAMA)
    except Exception:
        print("FAIL embeddings server DOWN at %s  -> recall is impossible (LESSON 2)" % OLLAMA)
        ok = False
    try:
        d = json.loads(urllib.request.urlopen(QDRANT + "/collections/" + COLL, timeout=5).read())
        n = d["result"]["points_count"]
        print("OK   collection %s: %d points, status %s" % (COLL, n, d.get("status")))
        if n == 0:
            print("FAIL collection is EMPTY - run index_memory.py")
            ok = False
    except Exception:
        print("FAIL collection %s not reachable at %s (LESSON 1)" % (COLL, QDRANT))
        ok = False
    return ok


def main():
    tests = sys.argv[1:] or DEFAULT_TESTS
    if not health():
        sys.exit(1)
    worst = 1.0
    for t in tests:
        hits = search(embed(t), 3, None)
        top = hits[0]["score"] if hits else 0.0
        worst = min(worst, top)
        print("\nQ: %s" % t)
        for h in hits:
            p = h["payload"]
            print("   [%.3f] %s :: %s" % (h["score"], p.get("source"), (p.get("heading") or "")[:80]))
        if not hits:
            print("   NO HITS")
    print("\nworst top-score: %.3f  %s" % (worst, "(healthy)" if worst >= 0.3 else "(WEAK - reindex or check embedder)"))
    sys.exit(0 if worst >= 0.3 else 2)


if __name__ == "__main__":
    main()
