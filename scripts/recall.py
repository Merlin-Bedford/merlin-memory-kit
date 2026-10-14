#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MERLIN MEMORY KIT - recall.py
Semantic search over your memory collection. THE DISCIPLINE (LESSON 7):
query this BEFORE any build/download/install. If it's in memory, use it.

Usage:
  python recall.py "your question" [--k 5] [--filter source=memory/2026-10-10.md]
Exit codes: 0 hits, 3 no hits, 2 service down (so agents can branch on it).
By Merlin the Owl - MIT licensed.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load

CFG = load()
QDRANT, OLLAMA, MODEL, COLL = CFG["qdrant_url"], CFG["ollama_url"], CFG["embedding_model"], CFG["collection"]


def embed(text):
    for lim in (8000, 3000, 1200):
        try:
            body = json.dumps({"model": MODEL, "prompt": text[:lim]}).encode()
            r = urllib.request.Request(f"{OLLAMA}/api/embeddings", data=body,
                                       headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=60).read())["embedding"]
        except Exception as e:
            err = e
    raise err


def search(vector, k, flt):
    body = {"vector": vector, "limit": k, "with_payload": True}
    if flt:
        key, val = flt.split("=", 1)
        body["filter"] = {"must": [{"key": key, "match": {"value": val}}]}
    r = urllib.request.Request(f"{QDRANT}/collections/{COLL}/points/search",
                               data=json.dumps(body).encode(), method="POST",
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read())["result"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--filter", help='payload filter, e.g. source=MEMORY.md')
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # preflight, because silent recall death is the whole reason this kit exists.
    # Say WHICH thing is down, and what to run - a vague "not reachable" costs an hour.
    try:
        urllib.request.urlopen(OLLAMA + "/api/version", timeout=5).read()
    except Exception:
        print("DOWN: embeddings server not reachable at %s (LESSON 2)" % OLLAMA)
        sys.exit(2)
    try:
        qdrant_coll = json.loads(urllib.request.urlopen(QDRANT + "/collections/" + COLL, timeout=5).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("MISSING: collection '%s' does not exist on %s. Run index_memory.py first, "
                  "or set \"collection\" in kit.config.json to the one you already have." % (COLL, QDRANT))
            sys.exit(3)
        print("DOWN: Qdrant answered HTTP %s at %s (LESSON 1)" % (e.code, QDRANT))
        sys.exit(2)
    except Exception:
        print("DOWN: Qdrant not reachable at %s - run the launcher (LESSON 1)" % QDRANT)
        sys.exit(2)
    if (qdrant_coll.get("result") or {}).get("points_count", 0) == 0:
        print("EMPTY: collection '%s' exists but has 0 points - run index_memory.py" % COLL)
        sys.exit(3)

    t0 = time.time()
    hits = search(embed(args.query), args.k, args.filter)
    if args.json:
        print(json.dumps([{"score": round(h["score"], 4), **h["payload"]} for h in hits],
                         ensure_ascii=False, indent=1))
    elif not hits:
        print("no hits")
    else:
        for h in hits:
            p = h["payload"]
            print("[%.3f] %s :: %s" % (h["score"], p.get("source"), (p.get("heading") or "")[:90]))
        print("(%d hits in %.2fs)" % (len(hits), time.time() - t0))
    sys.exit(0 if hits else 3)


if __name__ == "__main__":
    main()
