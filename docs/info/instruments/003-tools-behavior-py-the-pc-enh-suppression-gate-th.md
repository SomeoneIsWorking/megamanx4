---
id: I003
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/behavior.py — the pc_enh suppression-map gate

## Validated by

All three X4 enhancements have `affect: full`, so the map must state that the typed comparison role
force-suppresses them. The instrument is validated in both directions by `--selftest`: a synthetic
entry with a suppression guard passes, the same entry without it fails, and an empty corpus refuses.
Every result prints the number of deviations and canon-affecting entries inspected. The real map
currently checks three deviations. Blind spot: this tool validates the map, not the call site; the
shipping `x4::enh()` contract is exercised separately by `x4_runtime` using
`psx::config::ScopedDiagnosticRun`.

## Known failure modes

(none recorded yet)
