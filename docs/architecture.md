# Architecture

## Goal

PATCH V0 is built so the core logic survives the jump from a terminal prototype to a Raspberry Pi robot head.

## Runtime shape

The app uses one main orchestrator with replaceable adapters.

- `orchestrator`: owns the conversation loop and command handling
- `brain`: builds prompts, calls the chat provider, and coordinates summary and fact extraction
- `memory`: stores turns, summaries, facts, tasks, model runs, and metadata in SQLite
- `providers`: local model integrations, starting with Ollama
- `adapters`: input and output backends
- `personality`: system prompt and default PATCH persona
- `config`: app and model-profile loading

## Data flow

1. Input adapter returns normalized user text.
2. Orchestrator checks for slash commands.
3. Brain retrieves compact memory context.
4. Chat provider generates a reply with the active model profile.
5. Output adapter prints the reply.
6. Memory store saves the turn.
7. Summary and fact extraction update long-term memory.

## Why memory is split

PATCH does not resend the full conversation history to the model. Instead it uses:

- recent turns for local continuity
- a rolling summary for older context
- a fact store for durable personal memory

This keeps prompts small and response quality more stable over long sessions.

## Why Ollama is first

Ollama makes local model testing much easier because:

- models are easy to swap
- the API is stable and simple
- setup is reproducible for other collaborators

The provider interface keeps the system ready for future runtimes such as `llama.cpp`.
