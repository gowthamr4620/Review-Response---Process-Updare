# Candere A/B Test: Grounding Instruction vs. Persona-Only

Answers the open question: does adding a Grounding Instruction measurably
reduce repetition versus relying on the persona paragraph alone? Same tone
(Conversational), same length (80 words), same signature (business name),
same 30 sampled reviews, same everything else - only variable changed is
the presence/absence of the Grounding Instruction section.

## Run it

```
export ANTHROPIC_API_KEY=sk-ant-...
python run_ab_test.py
python diagnose_ab.py output/ab_test_output.csv
```

This calls the real Anthropic API (30 reviews x 2 variants = 60 calls) and
writes `output/ab_test_output.csv`, then prints a side-by-side diagnostic:
opening-word distribution, "greet then thank" structural pattern frequency,
top word frequency, and 5 sample responses per variant so you can read
actual quality, not just the stats.

## What to look for

- If Variant A (no grounding) and Variant B (with grounding) show similar
  opening-word concentration and similar top-word frequency -> the persona
  paragraph is doing enough of the job on its own, grounding instruction
  isn't earning its keep, drop it and keep the prompt leaner.
- If Variant A shows meaningfully higher concentration on a small set of
  words/openings than Variant B -> grounding instruction is doing real work,
  keep it.
- Read the printed samples, not just the stats - a lower repetition score
  with worse-quality responses isn't actually a win.
