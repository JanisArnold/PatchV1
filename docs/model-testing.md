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

- keep `default` as the current winning local production-style model
- keep model-named profiles for testing and comparison
- avoid planning around many simultaneously loaded local models
- use `/benchmark` as a rough speed/comparison tool, not the only decision tool
