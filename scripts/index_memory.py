#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MERLIN MEMORY KIT - index_memory.py
Chunk memory .md files by '## ' heading, subdivide long sections, embed locally
(Ollama), upsert into Qdrant. Safe: additive by default; --rebuild recreates the
collection; --dry-run computes everything but writes nothing.

Lessons baked in (see docs/LESSONS.md):
  - embed with graded length fallback (8000 -> 3000 -> 1200) so long chunks never fail the run
  - payload indexes on source/indexed_at for filtered recall
  - vectors are reproducible: a text dump is written next to backups, vectors are not

Usage:
  python index_memory.py [--rebuild] [--dry-run] [--days N]
By Merlin the Owl - MIT licensed.
"""
import argparse, json, os, re, sys, time, urllib.request, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load

CFG = load()
QDRANT = CFG["qdrant_url"]
OLLAMA = CFG["ollama_url"]
MODEL = CFG["embedding_model"]
VEC = CFG["vector_size"]
COLL = CFG["collection"]
WS = CFG["workspace_dir"]


def qdrant(path, method="GET", body=None, timeout=90):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{QDRANT}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def embed(text, tries=3):
    last = None
    for lim in (8000, 3000, 1200):
        try:
            body = json.dumps({"model": MODEL, "prompt": text[:lim]}).encode()
            r = urllib.request.Request(f"{OLLAMA}/api/embeddings", data=body,
                                       headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=120).read())["embedding"]
        except Exception as e:
            last = e
    for _ in range(tries):
        try:
            body = json.dumps({"model": MODEL, "prompt": text[:1200]}).encode()
            r = urllib.request.Request(f"{OLLAMA}/api/embeddings", data=body,
                                       headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(r, timeout=120).read())["embedding"]
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def embed_pieces(chunk, size=700):
    """Last-resort recovery: a chunk the embedder refuses gets split on line boundaries
    and embedded piecewise, so one awkward section never costs you memory."""
    lines, out, buf = chunk.split("\n"), [], ""
    for ln in lines:
        if len(buf) + len(ln) + 1 > size and buf:
            out.append(buf)
            buf = ""
        buf += (("\n" if buf else "") + ln)
    if buf.strip():
        out.append(buf)
    vecs = []
    for piece in out:
        try:
            vecs.append(embed(piece))
        except Exception:
            pass
    return vecs


def subdivide(chunk, limit=1100, target=850):
    """Long ## sections get split on paragraph boundaries so recall stays precise."""
    if len(chunk) <= limit:
        yield chunk
        return
    buf = ""
    for p in chunk.split("\n\n"):
        if len(buf) + len(p) + 2 > target and buf:
            yield buf.strip()
            buf = ""
        buf += ("\n\n" if buf else "") + p
    if buf.strip():
        yield buf.strip()


def chunks_for(text, source):
    now = time.strftime("%Y-%m-%d %H:%M")
    for part in re.split(r"(?=^## )", text, flags=re.MULTILINE):
        part = part.strip()
        if len(part) < 40:
            continue
        head = part.split("\n")[0].lstrip("#").strip()[:200]
        for i, sub in enumerate(subdivide(part)):
            if len(sub) < 60:
                continue
            h = head if i == 0 else "%s (cont %d)" % (head, i)
            yield sub, {"source": source, "heading": h, "chars": len(sub), "indexed_at": now}


def gather_files(days):
    files = [(f, f) for f in CFG.get("index_files", [])]
    memdir = os.path.join(WS, CFG.get("daily_notes_dir", "memory"))
    if os.path.isdir(memdir):
        notes = sorted(f for f in os.listdir(memdir) if f.endswith(".md"))
        limit = days or CFG.get("daily_notes_max", 14)
        for fn in notes[-limit:]:
            files.append((os.path.join(memdir, fn), "memory/" + fn))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="drop and recreate the collection first")
    ap.add_argument("--dry-run", action="store_true", help="chunk + embed, write nothing")
    ap.add_argument("--days", type=int, default=0, help="override daily-note window")
    args = ap.parse_args()

    # preflight: both services must be up or recall will be broken anyway (LESSON 2)
    try:
        urllib.request.urlopen(OLLAMA + "/api/version", timeout=5).read()
    except Exception:
        sys.exit("FATAL: Ollama not reachable at %s - embeddings down = memory down (docs/LESSONS.md #2)" % OLLAMA)
    if not args.dry_run:
        try:
            qdrant("/collections", "GET", timeout=10)
        except Exception:
            sys.exit("FATAL: Qdrant not reachable at %s - start it first (launchers/)" % QDRANT)

    files = gather_files(args.days)
    print("files to index:", len(files))

    if args.rebuild and not args.dry_run:
        print("recreating collection", COLL)
        qdrant(f"/collections/{COLL}", "DELETE")
        time.sleep(2)
    if args.dry_run:
        print("dry run: collection untouched")
    else:
        try:
            qdrant(f"/collections/{COLL}", "GET")
        except Exception:
            r = qdrant(f"/collections/{COLL}", "PUT",
                       {"vectors": {"size": VEC, "distance": "Cosine"},
                        "shards_number": 1, "replication_factor": 1})
            print("collection created:", r.get("status"))
            for fld in ("source", "indexed_at"):
                try:
                    qdrant(f"/collections/{COLL}/index", "PUT",
                           {"field_name": fld, "field_type": "keyword"}, 60)
                except Exception as e:
                    print("payload index skip (%s): %s" % (fld, str(e)[:60]))

    t0, pts, fail, total = time.time(), [], 0, 0
    for path, source in files:
        full = path if os.path.isabs(path) else os.path.join(WS, path)
        if not os.path.exists(full):
            print("  skip (missing):", source)
            continue
        text = open(full, encoding="utf-8", errors="replace").read()
        for chunk, meta in chunks_for(text, source):
            try:
                v = embed(chunk)
                recs = [(v, meta)]
            except Exception as e:
                # don't lose the section: split it and index the pieces instead
                pieces = embed_pieces(chunk)
                if not pieces:
                    fail += 1
                    print("  embed FAIL", source, str(e)[:60])
                    continue
                print("  split-recovered:", source, "::", meta["heading"][:50],
                      "(%d pieces)" % len(pieces))
                recs = []
                for j, v in enumerate(pieces):
                    m2 = dict(meta)
                    m2["heading"] = "%s (piece %d)" % (meta["heading"], j + 1)
                    recs.append((v, m2))
            total += len(recs)
            if args.dry_run:
                continue
            for v, meta2 in recs:
                pts.append({"id": str(uuid.uuid4()), "vector": v, "payload": meta2})
                if len(pts) >= 32:
                    qdrant(f"/collections/{COLL}/points", "PUT", {"points": pts, "wait": True}, 120)
                    pts = []
    if pts and not args.dry_run:
        qdrant(f"/collections/{COLL}/points", "PUT", {"points": pts, "wait": True}, 120)

    if args.dry_run:
        print("\nDRY RUN: %d chunks embeddable, %d failed in %.0fs (nothing written)"
              % (total, fail, time.time() - t0))
        return
    res = qdrant(f"/collections/{COLL}")["result"]
    print("\nDONE in %.0fs: indexed=%d failed=%d collection points=%s status=%s"
          % (time.time() - t0, total, fail, res["points_count"], res["status"]))
    print("Now run backup.py - memory you cannot restore is memory you risk (LESSON 5).")


if __name__ == "__main__":
    main()
