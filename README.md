# Review Response Prompt System - Test Harness

## What this is
A runnable version of the redesigned review-response prompt system, built to
be tested with Claude Code using your own API key across 6 real clients.

## Structure
```
config/
  client_config_schema.py   - config data model (tone/length enums, validation)
  persona_pools.py          - platform-owned, one persona per tone (not client-editable)
  clients.py                - real config for 6 clients
scripts/
  build_prompt.py           - the prompt builder itself
  run_batch.py               - calls the LLM API across all clients' review files
  diagnose_repetition.py     - checks output for repetition patterns
data/
  (each client's review export, referenced from clients.py)
output/
  (generated CSVs land here)
```

## Before running

1. Set your API key as an environment variable - never paste it into a file:
   ```
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
   or
   ```
   export OPENAI_API_KEY=sk-...
   ```

## Running

Quick iteration (30 sampled reviews per client):
```
python scripts/run_batch.py --provider anthropic --sample 30
```

Single client only:
```
python scripts/run_batch.py --provider anthropic --sample 30 --client candere
```

Full run, all clients, all reviews:
```
python scripts/run_batch.py --provider anthropic
```

## Diagnosing output

Per-client file:
```
python scripts/diagnose_repetition.py output/candere_output.csv
```

Cross-client check:
```
python scripts/diagnose_repetition.py output/combined_output.csv --by-client
```

## What to look for in the diagnostic output

- Opening word share above ~30% = still converging
- "Greet then thank" pattern above ~15% = old skeleton leaking through
- Any 5+ letter word in >40% of one client's responses = new stock phrase

## Iterating

1. Run a sample batch.
2. Run the diagnostic.
3. If flagged, adjust the relevant prompt section in `build_prompt.py`.
4. Re-run and re-diagnose until flags clear.
