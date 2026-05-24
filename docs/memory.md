# Memory

## Storage

PATCH stores long-term data in a local SQLite database.

Default path:

- `data/patch.db`

## Tables

- `sessions`: top-level chat runs
- `turns`: user and assistant messages
- `summaries`: rolling summaries of older context
- `facts`: durable extracted memories
- `tasks`: placeholder for future structured actions
- `model_runs`: benchmark and model-performance records
- `meta`: schema and app metadata

## Retrieval strategy

For each reply, PATCH retrieves:

- the latest few turns
- the most recent summary
- the most relevant facts

It does not send the full conversation history to the model.

## Fact extraction

V0 uses a hybrid strategy:

- rule-based extraction for obvious user facts
- optional model-assisted extraction when the extraction profile is available

Facts are stored as:

- subject
- predicate
- value
- confidence
- source turn id

## Summary updates

Every configured number of turns, PATCH updates a rolling summary. This keeps context compact while preserving longer-term continuity.
