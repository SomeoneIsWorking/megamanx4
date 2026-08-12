---
id: I001
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/verify_decomp_targets.py — does the vendored AGPL decomp target OUR disc's bytes, per module?

## Validated by

Validated in BOTH directions on real data 2026-08-12. POSITIVE: 1/1 splat config discovered and MATCHED against the real disc (mmx4 declares exactly one code segment, so 1 is the whole denominator, not a sample). NEGATIVE: --selftest substitutes 40 zeros for the first target's expected hash and the run prints exactly one MISMATCH line and exits 1 — so the tool demonstrably CAN report the other answer. REFUSALS, both coded and reachable: exit 2 when external/mmx4 is absent ("This run compared NOTHING"), and exit 2 when ZERO usable splat configs are discovered (printing how many *.splat.yaml files were nonetheless present). Every run prints its denominators: configs discovered / matched / mismatched / unchecked / extract-failed, and disc code images present vs covered. A config whose check.<variant>.txt is missing is counted as UNCHECKED and makes the run exit 1 — it is never silently dropped.

## Known failure modes

(none recorded yet)
