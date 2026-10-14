#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MERLIN MEMORY KIT - backup.py
Two backup kinds, because one is not enough (LESSON 5):
  1. Qdrant native snapshot  -> directly restorable, binary
  2. text/metadata dump      -> greppable JSONL, survives any Qdrant version
Rotates: keeps newest N of each kind (config: backup_keep).

Usage: python backup.py [--dest DIR]
By Merlin the Owl - MIT licensed.
"""
import argparse, json, os, shutil, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _config import load

CFG = load()
QDRANT, COLL = CFG["qdrant_url"], CFG["collection"]
DEST = os.path.abspath(os.path.join(CFG["workspace_dir"], CFG.get("backup_dir", "kit_backups"))) \
    if not CFG.get("backup_dir", "").startswith("/") else CFG["backup_dir"]
KEEP = CFG.get("backup_keep", 6)
SNAP_DIR = CFG.get("qdrant_snapshot_dir")  # set if your qdrant storage path is non-default


def req(url, method="GET", body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=DEST)
    args = ap.parse_args()
    dest = args.dest
    os.makedirs(dest, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")

    # 1. native snapshot
    try:
        snap = req(f"{QDRANT}/collections/{COLL}/snapshots?wait=true", "POST")["result"]
        name = snap["name"]
        cands = ([os.path.join(SNAP_DIR, COLL, name)] if SNAP_DIR else []) + [
            os.path.join(os.getcwd(), "snapshots", COLL, name),
            os.path.join("snapshots", COLL, name),
        ]
        src = next((c for c in cands if os.path.exists(c)), None)
        if src:
            dst = os.path.join(dest, "snapshot_%s_%s.snapshot" % (COLL, ts))
            shutil.copy2(src, dst)
            print("snapshot ->", dst, "(%.1f MB)" % (os.path.getsize(dst) / 1e6))
        else:
            print("snapshot created (%s) but file not found near qdrant's cwd;" % name)
            print("        set qdrant_snapshot_dir in kit.config.json to your storage path")
    except Exception as e:
        print("snapshot FAILED:", str(e)[:120])

    # 2. text dump (no vectors - they are reproducible from source files)
    pts, off = [], None
    for _ in range(1000):
        body = {"limit": 128, "with_payload": True}
        if off:
            body["offset"] = off
        d = req(f"{QDRANT}/collections/{COLL}/points/scroll", "POST", body)["result"]
        pts.extend(d.get("points", []))
        off = d.get("next_page_offset")
        if not off:
            break
    txt = os.path.join(dest, "memory_text_%s.jsonl" % ts)
    with open(txt, "w", encoding="utf-8") as f:
        for p in pts:
            pl = p.get("payload", {})
            f.write(json.dumps({"id": p["id"], "source": pl.get("source"),
                                "heading": pl.get("heading"), "chars": pl.get("chars"),
                                "indexed_at": pl.get("indexed_at")}, ensure_ascii=False) + "\n")
    print("text dump ->", txt, len(pts), "records")

    # 3. rotation
    for pref in ("snapshot_", "memory_text_"):
        fs = sorted([f for f in os.listdir(dest) if f.startswith(pref)], reverse=True)
        for old in fs[KEEP:]:
            os.remove(os.path.join(dest, old))
            print("rotated out:", old)

    print("\nbackups now in", dest)
    for f in sorted(os.listdir(dest)):
        print("  ", f)
    print("Schedule this weekly (cron/task). Memory only counts if it survives the machine. (LESSON 5)")


if __name__ == "__main__":
    main()
