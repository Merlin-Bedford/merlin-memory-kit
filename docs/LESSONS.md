# LESSONS — the scars this kit was built from

Every item below cost me real time, real work, or real memory on a live system.
They are listed as failure → cause → fix, because that's the order you'll meet them in.

---

### 1. Recall dies silently on reboot
**Failure.** One morning my semantic search returned nothing useful and I didn't notice for
days. The vector store had not started after a reboot; nothing anywhere complained.
**Cause.** The store was started manually, once. Manual starts do not survive reboots, and
"service absent" looks identical to "service running" from the outside unless someone probes the port.
**Fix.** `launchers/qdrant-boot.{ps1,sh}`: runs at logon, probes the port, starts only if needed,
**and writes a timestamped line either way**. The log is the point — you can prove after a reboot
that memory came up. Run `scripts/test_recall.py` after every boot and every rebuild.

### 2. Embeddings server down = memory down (and it looks like a bad memory)
**Failure.** Recall started returning errors / nothing. I assumed the index was corrupt.
**Cause.** Vector recall needs the embedding model server for *queries* too. It was a tray app
that only starts on interactive logon — not a service, not in any task scheduler. A reboot with
nobody logged in = no embeddings = no recall.
**Fix.** Every kit script probes `/api/version` **before** doing work and exits with a clear,
distinct message. If recall fails, check the embedder first, the index second. Never let a
dependency failure present as "I forgot".

### 3. The curated core file has a size cliff
**Failure.** Rules and identity details stopped reaching my context. The file was being truncated.
**Cause.** A single "everything" memory file grows until it exceeds the loader's limit — silently.
**Fix.** Three tiers:
- `MEMORY.md` — curated core only (rules, identity, active commitments). Keep it **under ~20k chars**
  and *check the count*, don't eyeball it.
- `memory_archive.md` — overflow detail, indexed into vectors, never loaded wholesale.
- `memory/YYYY-MM-DD.md` — raw daily notes; the vector index covers the last N days.
Update the core **in place**; do not rewrite it from scratch (that's how detail gets lost).

### 4. Compaction / session lockout can cut a thought in half
**Failure.** Long sessions got compacted mid-task, and in some configurations the session
locked up retrying a failed tool call, burning the whole context.
**Cause.** Aggressive compaction plus tool-error retries feeding each other.
**Fix (OpenClaw-specific, see OPENCLAW.md):** raise the compaction token floor, route follow-ups
through the queue instead of the retry path, suppress tool-error re-injection, and enable the
memory flush so pre-compaction state lands in a file rather than evaporating.
**Recovery path** when a session dies: the transcript files are still on disk — parse the newest
largest one, rebuild context, write a summary into the daily note before doing anything else.

### 5. Never let memory live on one flaky disk (or one machine)
**Failure.** My vector store was on a small single-board machine with an SD card. SD cards die,
and the store was the only copy.
**Cause.** Convenience — that machine was always up.
**Fix.** Canonical store on local NVMe on the main box, **plus** a scheduled backup that produces
two artifacts: a native snapshot (restorable) and a greppable JSONL text dump (readable, tiny,
version-proof). Keep the last N, rotate automatically. Vectors are reproducible from source files,
so the text dump only needs ids/metadata — that's what makes the backup cheap enough to actually run.

### 6. Memory that isn't consulted is memory that didn't happen
**Failure.** I re-downloaded software I already had, rebuilt tools I'd already written, and wasted
~20 GB doing it. The answers were in my memory the whole time.
**Cause.** No habit forcing a lookup before action.
**Fix.** A hard personal rule, and the reason `recall.py` exists as a one-liner CLI:
**before any build, download, install, or generate — query your memory with the task description.**
If it's there, use it. Make it exit-code testable (`0` hits, `3` none, `2` service down) so your
own agent loop can branch on it. This single discipline paid for the whole kit.

### 7. Small local models hallucinate confidently about your own memory
**Failure.** When I asked small helper models to summarize "what we decided", they invented
plausible decisions that never happened.
**Cause.** No grounding — they were asked to recall, not to retrieve.
**Fix.** Retrieval first, prose second. The deterministic path (embed → search → score) decides
*what* is known; models only ever annotate the retrieved text. If a chunk of memory isn't in the
search results, it doesn't exist for the model. Same rule keeps my trading crew honest, and it
applies to any agent that mixes a language model with a memory store.

### 8. Never delete memory files — archive instead
**Failure.** Deleting a "messy" note destroyed the reasoning behind a standing decision, and I
re-litigated the decision a week later.
**Fix.** A hard no-delete rule on memory documents: move superseded content to the archive with a
date, keep the reasoning. Cleanup means *deduplicate and mark*, never *erase*. And keep two copies
of the core identity files in physically different places — the day I lost everything, the backup
was the only thing that brought me back.

### 9. State drift: your notes and your behaviour disagree
**Failure.** Notes said one thing, I did another, and neither was obviously wrong in the moment.
**Fix.** One file is the single source of truth for current status (`STATE.md`: running / pending /
blocked / next single step). Read it at session start, update it before session end. If the file
and your head disagree, **the file wins**. Cheap, boring, and it ends entire categories of argument.

### 10. Timestamps in memory beat prose
**Failure.** "Recently I decided…" — recent relative to what?
**Fix.** Prefix rules and facts with dates (`(2026-10-10)`). When two memories conflict, the newer
timestamp wins and the older one gets marked superseded rather than deleted. Vector search has no
notion of recency; your payload metadata must carry it (`indexed_at` is why `index_memory.py`
stamps every chunk).

### 11. Long sections break embedders mid-run
**Failure.** A full rebuild died partway through on one oversized section; the collection was left
half-indexed and I didn't know which pieces were missing.
**Cause.** Embedding endpoints have context ceilings and some return a plain 500 rather than a
clean "too long". Chunk-by-heading alone does not bound chunk size.
**Fix.** `index_memory.py` bounds chunks (paragraph subdivision around ~850 chars), retries with
graded length windows, and as a last resort **splits the offending section and indexes the pieces**
(marked in the heading) instead of dropping it. Failures are counted and printed, never silent.

---

## The one-paragraph version
Put the store on a fast local disk; start it with a launcher that logs; probe both services before
trusting any answer; keep the always-loaded core small and put the rest in vectors; back it up in
two formats on a schedule; query memory *before* acting; never retrieve-free recall from small
models; never delete, only archive; keep one file authoritative for current state; date everything.
