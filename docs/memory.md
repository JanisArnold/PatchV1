# Memory

## Design

The goal: PATCH remembers everything, but only the *relevant* slice enters the prompt each turn, so the context stays short and inference stays fast. Three tiers:

1. **Short-term — rolling context.** The last few conversation turns, kept verbatim in the prompt. Cheap, immediate.
2. **Episodic — retrievable past exchanges.** Every exchange is indexed in the background. At query time, the top-3 most relevant past exchanges are injected into the prompt with their timestamps, so PATCH can reason about *when* things happened.
3. **Facts — SQLite.** Structured, always-true facts (name, preferences, standing instructions), matched against the current message with FTS5/BM25 and prepended to the system prompt.

Per-turn prompt = persona + facts + top-3 episodes + rolling context + new message. Lean, bounded, fast.

## Episodic backends

- `keyword` (default): SQLite FTS5 full-text search with BM25 ranking over the `episodes` table. Zero extra dependencies (FTS5 ships inside SQLite), and ranking happens in SQL instead of Python, so it stays fast as history grows. The latest few episodes are excluded from results because they already sit in the rolling context.
- `lancedb`: disk-based vector search with `all-MiniLM-L6-v2` embeddings (`pip install lancedb sentence-transformers`). This is the spec target on the Pi: LanceDB memory-maps its data, so episodic memory can grow indefinitely without competing with the LLM for RAM. Embeddings are computed on the background worker thread, never on the hot path.

Select via `memory.episodic_backend` in the config.

## Storage

PATCH stores long-term data in a local SQLite database (WAL mode).

Default path:

- `data/patch.db` (with `-wal`/`-shm` sidecar files)
- `data/lancedb/` when the LanceDB backend is active

## Tables

- `sessions`: top-level chat runs
- `turns`: user and assistant messages
- `episodes` (+ `episodes_fts`): indexed exchanges for episodic retrieval
- `summaries`: rolling summaries of older context, each anchored to the last turn it covers
- `facts` (+ `facts_fts`): durable extracted memories
- `meta`: schema and app metadata

The `_fts` tables are FTS5 indexes kept in sync by SQL triggers; opening an older database migrates and backfills them automatically. Performance data lives in `data/perf.jsonl` (see [Operations](operations.md)), not in the database.

## Retrieval strategy

For each reply, PATCH retrieves:

- the latest few turns
- the most recent summary (skipped for smalltalk)
- the most relevant facts, ranked by BM25 against the new message
- the top-3 most relevant episodic memories (skipped for smalltalk)

It never sends the full conversation history to the model. Retrieval is deliberately aggressive (top-3, not top-10): a shorter prompt directly cuts prompt-eval time on the Pi.

## Summary updates and fact extraction (distillation)

Once the number of turns since the last summary reaches `summary_turn_window`, the background worker runs **one** LLM call — the `MemoryDistiller` — that does both jobs at once:

- folds the recent turns into the rolling summary
- lists durable user facts as structured `FACT: subject | predicate | value` lines

One prompt, two outputs: half the background load on the shared `llama-server`, and the LLM extracts far cleaner facts than regex patterns can. Facts are stored as subject / predicate / value / confidence / source turn id. Each summary records the id of the last turn it covers, so the trigger never drifts.

The worker waits for the foreground to go idle before running the distillation, so it never slows down a reply the user is waiting for.

## Planned: consolidation

A background consolidation job will periodically summarize old episodic memories into compact SQLite facts — mimicking how human memory turns episodes into durable knowledge. This keeps retrieval sharp as history grows.
