# Model Testing

PATCH treats model testing as part of the platform, not a one-off experiment.

The canonical model-testing workflow now lives here:

- [Testing Guide](testing.md)

Use that page for:

- command reference
- clean model comparison flow
- benchmark behavior
- prompt sets
- winner-selection criteria

## Short version

- keep `default` as the current winning local production-style model (`gemma-4-e2b-it-qat-q4_0` for the Pi)
- always prefer official `-qat-` checkpoints over community PTQ quants of the base model: QAT models learned to live with 4-bit rounding during training, so they perform near the 16-bit baseline at the same RAM cost
- keep model-named profiles for testing and comparison (Unsloth `UD-Q4_K_XL` is worth comparing against the Q4_0)
- avoid planning around many simultaneously loaded local models
- use `/benchmark` as a rough speed/comparison tool, not the only decision tool
- once the pipeline is stable, benchmark with and without speculative decoding (`-md` drafter flag on `llama-server`)
