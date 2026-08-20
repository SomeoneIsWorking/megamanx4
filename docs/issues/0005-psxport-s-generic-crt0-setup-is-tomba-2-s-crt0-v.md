---
id: 5
title: psxport's original crt0_setup encoded Tomba!2's crt0 instead of a generic contract
status: resolved
symptom: X4's fully measured crt0 group could not be represented without wrong stack and heap state.
tags: framework,boot,crt0,residence-defect,re-01
created: 2026-08-12
updated: 2026-08-21
---

## Root cause

The original framework hardcoded four Tomba!2-specific facts: stack bias `-8`, two unconditional
heap-global stores, and only `a0` live at the InitHeap dispatch. X4 measures bias `0`, has neither
heap global, and passes the heap size in `a1`. Leaving the optional addresses zero therefore wrote
twice to guest address zero, while any invented nonzero address would have been a bandaid.

The result came from the same static extractor over both retail executables, not from copying the
matching decomp. `tools/verify_crt0.py` records every absolute store and uses Tomba!2 as an independent
cross-control.

## Resolution

psxport `726d10c9` introduced `Crt0Plan`: a declared per-game stack bias, optional heap stores, and
the correct `a1` assignment. X4 now ships its measured boot group. On 2026-08-21:

- `verify_crt0.py --check` matched 19 shipping facts and located 15/15 framework mechanisms;
- the local selftest passed 25/25;
- the Tomba!2 cross-control passed 28/28.

RE-01 is therefore `re-verified`. Runtime boot remains downstream of the still-empty RE-02 seed set.
