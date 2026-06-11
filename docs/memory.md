# Memory

## Design

The goal: PATCH remembers everything, but only the *relevant* slice enters the prompt each turn, so the context stays short and inference stays fast. Three tiers:

1. **Short-term — rolling context.** The last few conversation turns, kept verbatim in the prompt. Cheap, immediate.
2. **Episodic — retrievable past exchanges.** Every exchange is indexed in the background. At query time, the top-3 most relevant past exchanges are injected into the prompt with their timestamps, so PATCH can reason about *when* things happened.
3. **Facts — SQLite.** Structured, always-true facts (name, preferences, standing instructions), scored against the current message by token overlap and prepended to the system prompt.

Per-turn prompt = persona + facts + top-3 episodes + rolling context + new message. Lean, bounded, fast.

## Episodic backends

- `keyword` (default): token-overlap retrieval over the SQLite `episodes` table. Zero extra dependencies, works everywhere. The latest few episodes are excluded from results because they already sit in the rolling context.
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
- `episodes`: indexed exchanges for episodic retrieval (keyword backend)
- `summaries`: rolling summaries of older context, each anchored to the last turn it covers
- `facts`: durable extracted memories
- `tasks`: placeholder for future structured actions
- `model_runs`: benchmark and model-performance records
- `performance_logs`, `system_snapshots`: timing and Pi health data
- `meta`: schema and app metadata

## Retrieval strategy

For each reply, PATCH retrieves:

- the latest few turns
- the most recent summary (skipped for smalltalk)
- the most relevant facts, ranked by token overlap with the new message
- the top-3 most relevant episodic memories (skipped for smalltalk)

It never sends the full conversation history to the model. Retrieval is deliberately aggressive (top-3, not top-10): a shorter prompt directly cuts prompt-eval time on the Pi.

## Fact extraction

A hybrid strategy:

- rule-based extraction for obvious user facts (runs in the background worker)
- optional model-assisted extraction when a `memory_extraction` profile is configured

Facts are stored as subject / predicate / value / confidence / source turn id.

## Summary updates

Once the number of turns since the last summary reaches `summary_turn_window`, the background worker folds them into a rolling summary. Each summary records the id of the last turn it covers, so the trigger never drifts.

## Planned: consolidation

A background consolidation job will periodically summarize old episodic memories into compact SQLite facts — mimicking how human memory turns episodes into durable knowledge. This keeps retrieval sharp as history grows.
