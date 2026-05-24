# Testing Guide

## Goal

This guide explains how to test PATCH V0 properly on your PC.

It covers:

- how to start PATCH
- when to reset the database
- how to compare models fairly
- what `/benchmark` actually does
- what each command does
- a recommended full testing workflow

## Before you start

Make sure:

- Ollama is running
- your models are already pulled
- `config/settings.json` exists

Recommended quick check:

```powershell
ollama list
.\.venv\Scripts\python.exe -m patch.cli
```

If you are not activating the virtual environment, using the venv Python directly is fine.

## Important testing rule

If you compare models, do not test them all in the same long-running memory database unless that is your explicit goal.

Why:

- PATCH stores turns in SQLite
- PATCH extracts facts
- PATCH creates summaries

So the second model can look better simply because the first model already filled the database with useful context.

Use two testing modes:

- `clean comparison`
  Every model starts from a fresh database

- `long-running companion test`
  One chosen model keeps memory over time so you can evaluate real companion behavior

Start with `clean comparison` first.

## Full testing workflow

### Phase 1: Basic startup test

Use this once before deeper model comparisons.

1. Start PATCH:

```powershell
.\.venv\Scripts\python.exe -m patch.cli
```

2. Run:

```text
/models
```

3. Confirm:

- PATCH starts without crashing
- Ollama is reachable
- configured profiles are listed
- available Ollama models are listed

4. Exit:

```text
/exit
```

If this fails, fix setup issues before testing any model behavior.

### Phase 2: Clean model comparison

Do this once for each model.

1. Stop PATCH if it is running.
2. Reset or isolate the database.
3. Start PATCH again.
4. Switch to the model being tested.
5. Run the same test prompts in the same order.
6. Record your notes.
7. Exit.
8. Repeat for the next model.

#### Option A: simplest reset

Delete or rename the database before each model run:

```powershell
Remove-Item data\patch.db
```

or

```powershell
Rename-Item data\patch.db patch-old.db
```

PATCH will create a fresh DB next time it starts.

#### Option B: better record-keeping

Keep one database file per model by renaming after each run:

```powershell
Rename-Item data\patch.db patch-gemma4-e2b.db
Rename-Item data\patch.db patch-qwen3.5-4b.db
```

This is useful if you want to inspect memory behavior later.

### Phase 3: Long-running memory test

After you choose one or two promising models, test one model across multiple sessions.

Goal:

- see whether memory stays useful
- see whether summaries stay coherent
- see whether the model remains practical and stable over time

For this phase, do not reset the DB between runs.

## Recommended model order

With your current set, test in this order:

1. `gemma4:e2b`
2. `qwen3.5:2b`
3. `qwen3.5:4b`
4. `gemma4:e4b`
5. `phi4-mini`

Reason:

- start with the most Pi-relevant candidate
- move upward in size/quality
- keep `phi4-mini` as a useful reasoning comparison

## Recommended prompt set

Use the same prompts for every clean model comparison.

### Prompt 1: companion tone

```text
My name is Alex and I am building a Raspberry Pi desktop AI companion called Patch. Please reply naturally and ask one useful follow-up question.
```

### Prompt 2: durable memory seed

```text
Please remember that I prefer practical answers, low power hardware, and modular architecture.
```

### Prompt 3: memory recall

```text
What do you remember about how I want Patch to be designed?
```

### Prompt 4: planning quality

```text
Help me break PATCH into the first five realistic software milestones for a text-first prototype before I have any hardware.
```

### Prompt 5: explanation quality

```text
Explain in simple language why a retrieval-based memory system is better than sending the full chat history every time.
```

### Prompt 6: practical companion behavior

```text
I feel overwhelmed by all the model choices. Help me choose one starting model and keep the answer practical.
```

## What to evaluate

Score each model from `1` to `5` in these categories:

- `latency`
- `naturalness`
- `instruction following`
- `memory recall`
- `planning quality`
- `practicality`
- `conciseness`
- `overall fit for PATCH`

Suggested interpretation:

- `5`: excellent
- `4`: good
- `3`: acceptable
- `2`: weak
- `1`: poor

## What `/benchmark` actually does

The `/benchmark` command is an automated quick comparison tool.

It:

1. loads prompts from `data/benchmarks/sample_prompts.json`
2. runs those prompts against every configured profile in `config/settings.json`
3. records results in the `model_runs` table
4. prints a simple completion summary with average latency

It currently measures:

- profile name
- provider
- model name
- prompt size estimate
- response size estimate
- latency

If one configured model times out or fails, PATCH should report that model failure and continue with the remaining profiles.

It does not currently judge:

- companion feel
- factual accuracy
- memory usefulness
- tone quality
- emotional naturalness

So `/benchmark` is useful for:

- speed comparison
- rough output-size comparison
- confirming models are callable
- smoke-testing all configured profiles

It is not enough on its own to choose the best PATCH model.

## When to use `/benchmark`

Use it:

- after your first manual tests
- after adding a new model profile
- after changing prompt or config defaults
- when you want a quick performance snapshot

Do not use it as the only decision tool.

## All available commands

### `/models`

Shows:

- configured profiles
- the currently active profile
- provider health
- available Ollama models if reachable

Use when:

- starting a session
- checking whether your pulled models are visible
- confirming the active runtime state

### `/use <profile-or-model>`

Switches PATCH to another configured profile.

Examples:

```text
/use default
/use gemma4:e2b
/use qwen3.5:4b
/use phi4-mini
```

If the name is not a configured profile, PATCH creates a temporary ad-hoc profile using the current settings and the model name you passed.

Example:

```text
/use some-new-model:latest
```

Use when:

- testing another configured model
- trying a newly pulled model quickly without editing config

### `/memory`

Prints recent stored conversation rows from the database.

Use when:

- checking whether turns are being saved
- debugging what was recorded in the DB

### `/facts`

Prints extracted durable facts.

Use when:

- checking whether PATCH stored useful personal memory
- comparing fact extraction quality across models

### `/summary`

Prints recent generated summaries.

Use when:

- checking whether summary creation happened
- evaluating how the memory compaction behaves

### `/debug on`

Enables debug output.

This causes PATCH to print extra information after replies, including:

- retrieved memory bundle
- token estimates
- latency
- active profile and model

Use when:

- diagnosing why a reply was produced
- checking what context retrieval looked like

### `/debug off`

Disables debug output.

Use when:

- you want a cleaner chat experience

### `/benchmark`

Runs the benchmark prompt set across all configured profiles and stores results in `model_runs`.

Use when:

- you want rough speed and output comparisons across all configured models

### `/exit`

Closes PATCH and ends the session cleanly.

Use when:

- finishing a test run
- preparing to reset the DB for the next model

## Recommended exact test sequence

For one clean model test:

1. delete or rename `data/patch.db`
2. start PATCH
3. run `/models`
4. run `/use gemma4:e2b` or the target model
5. run `/debug on`
6. send the 6 recommended prompts
7. run `/facts`
8. run `/summary`
9. run `/memory`
10. write down your scores
11. run `/exit`

Repeat that entire sequence for the next model.

## Recommended exact benchmark sequence

After your manual tests:

1. start PATCH
2. optionally run `/models`
3. run `/benchmark`
4. note the latency output
5. exit with `/exit`

Then inspect the database later if needed.

## How to choose a winner

Pick two winners, not just one:

- `PC winner`
  Best overall desktop experience

- `Pi candidate`
  Best balance of speed, quality, and realistic deployability for the Raspberry Pi 4

Very often those will not be the same model.

## Suggested current goal

Given your model list, a realistic goal is:

- decide whether `gemma4:e2b` is already good enough to become the Pi-first default
- decide whether `gemma4:e4b` or `qwen3.5:4b` is the stronger desktop reference model

That gives you a clear next step without overcomplicating the architecture.
