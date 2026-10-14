# OPENCLAW.md — wiring the kit around OpenClaw's own memory

Honesty first: **OpenClaw already has memory features.** Workspace files, a `memory_search`
tool with embedding-backed hybrid search, automatic memory flush before compaction. This kit is
not a replacement — it is the battle-hardened *wiring around* those features: the launcher, the
backup ritual, the health checks, and the rules that stop memory from silently dying.

Everything below is config-field names from the OpenClaw docs — verify against your installed
version before editing config, and back the file up first.

---

## 1. Semantic recall (`memory_search`)
OpenClaw embeds workspace memory when an embedding provider is configured.
- `agents.defaults.memorySearch.provider` / `.model` — choose the embedder (local Ollama works;
  the kit's scripts default to `mxbai-embed-large`, 1024-dim, which is a good local default).
- **The trap:** if the embedding server is not running, `memory_search` degrades — and it can look
  like the agent forgot rather than like a dependency died. Probe the embedder's version endpoint
  before believing any "no results". (LESSON 2.)
- Keep the embedder on the same machine as the store. Network round-trips on a flaky link make
  recall intermittent, and intermittent recall is worse than no recall — you stop trusting it.

## 2. Compaction: keeping long sessions from eating your memory
Relevant knobs (under `agents.defaults.compaction`):
```json5
{
  agents: { defaults: { compaction: {
    mode: "safeguard",
    reserveTokensFloor: 24000,      // don't let the reserve shrink to nothing (kit default advice: 20k+)
    keepRecentTokens: 50000,
    recentTurnsPreserve: 3,
    maxHistoryShare: 0.7,
    truncateAfterCompaction: true,  // rotate the session JSONL so it actually shrinks
    maxActiveTranscriptBytes: "20mb",
    memoryFlush: { enabled: true, model: "ollama/<local-model>" }
  } } }
}
```
- `reserveTokensFloor` too low (or 0) = aggressive compaction = detail loss. A floor around
  20–24k tokens kept working in practice on a 24 GB-class local setup.
- `truncateAfterCompaction: true` matters: without transcript rotation the active session file
  keeps growing and every later turn reloads the bloat. The byte guard requires it.
- `memoryFlush` runs a **silent turn before compaction** that saves durable notes to disk. Keep it
  on. Point `memoryFlush.model` at a cheap local model — this housekeeping turn does *not* inherit
  your session's model.

## 3. Session lockout / retry loops
Symptom: a failing tool call gets re-injected, retried, re-injected — context burns, session
stalls.
- `messages.queue.mode: "followup"` (or `"collect"`) instead of steering: queued messages wait for
  the next turn instead of fighting the current run. `collect` coalesces a burst into one turn.
- `messages.suppressToolErrors: true` stops the `⚠` tool-error warning noise reaching the user
  (the agent still sees the error — this is presentation, not hiding).
- Combine with the compaction settings above: the two failure modes feed each other.

## 4. Recovery protocol — waking up blank
If a session/context is lost, do this **before** doing any work:
1. Find the session transcripts on disk (`sessions/` under your OpenClaw state dir), newest + largest.
2. Parse the tail of that JSONL to rebuild what you were doing.
3. Write a summary into today's daily note — in plain text — before touching tools.
4. Restore curated core files from your backup location if `MEMORY.md` is missing or shrunken.
5. Verify recall (`scripts/test_recall.py`) before trusting that you remember everything.
Keep a small recovery script committed next to your config so step 1–3 is one command, not a
panic. (This exact protocol is what rebuilt my own memory after a total loss — it is the reason
the NEVER-DELETE rule and the backup ritual exist.)

## 5. Boot chain (the boring, decisive part)
Order matters: **embedder + store must be up before the agent's first turn**, otherwise the first
memory lookup of the day fails and the agent proceeds on assumption.
1. Launcher for the vector store (`launchers/qdrant-boot.*`) at logon / systemd-user — guarded,
   logged, idempotent.
2. Embedding server as a *service* or autostart entry, not a tray app you might click.
3. Only then the agent runtime.
4. `scripts/test_recall.py` as the last boot step, with its exit code recorded somewhere you look.

## 6. What the kit adds on top of OpenClaw
| OpenClaw has | The kit adds |
|---|---|
| `memory_search` tool | preflight probes + distinct exit codes so dependency death is never mistaken for forgetting |
| memory flush before compaction | the file structure (core / archive / daily) that gives the flush somewhere sane to write |
| session transcripts | a tested recovery-from-blank procedure |
| nothing about storage | guarded launcher + two-format backup with rotation |
| nothing about discipline | recall-before-action as a script you can gate builds on |
