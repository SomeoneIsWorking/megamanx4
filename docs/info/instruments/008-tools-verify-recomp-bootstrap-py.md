---
id: I008
kind: instrument
status: trusted
created: 2026-08-21
---

## Instrument

tools/verify_recomp_bootstrap.py

## Validated by

2026-08-21: --selftest 2/2 over retail SHA-1; real emit.py produced 6192 binary roots -> 7533 functions with crt0/gameMain and zero overlays, while an out-of-text seed was refused before emission

## Known failure modes

Static emission cannot reveal runtime-computed targets that all binary pointer/table scans miss; only
a booting port can surface those as `[recomp-MISS]`. The tool therefore proves the initial resident
substrate and generated interface, not seed-set completeness for every game path. It deliberately
refuses any executable whose SHA-1 is not the targeted USA retail image.
