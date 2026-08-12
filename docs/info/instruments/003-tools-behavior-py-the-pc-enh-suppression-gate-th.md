---
id: I003
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/behavior.py — the pc_enh suppression gate (the ONLY automated check that this port's canon-affecting enhancements stay ORACLE/SBS-suppressed)

## Validated by

This instrument matters more in this repo than in any other tree, because all three of X4's deliverables are affect=full and behavior.py check is the only thing asserting they are force-suppressed. Validated in BOTH directions 2026-08-12 by its own --selftest, 3 checks, 0 failed: POSITIVE — a synthetic affect=full entry WITH a guard citing suppression passes (exit 0); NEGATIVE — the SAME entry with the suppression clause removed FAILS with '✗ … affect=full but `guard` doesn't cite ORACLE/SBS force-suppression' (exit 1); NEGATIVE — an EMPTY corpus REFUSES (exit 2). Real run over the real map: 'ok — checked 3 deviations, 3 canon-affecting'. KNOWN FAILURE MODE FOUND IN THE COPY THIS WAS TAKEN FROM (Tomba2Engine/tools/behavior.py, the only copy in the workspace) AND FIXED HERE — see docs/issues/0002: load() did 'if not os.path.exists(DOC): return []', and cmd_check over that empty list printed '[behavior] ok — 0 deviations, 0 canon-affecting (all SBS-suppressed)' and exited 0, i.e. a certified clean bill of health over a corpus that does not exist. Three fixes made here: load() refuses non-zero on a missing map (except from `set`, which creates it); cmd_check refuses on zero entries; and every pass prints its denominator ('checked N deviations, M canon-affecting') rather than a bare 'ok'. BLIND SPOT, printed on every pass: this gate reads the MAP, not the code — it cannot see whether the suppression the guard describes is actually implemented at the call site. That half is the single chokepoint x4::enh() in game/core/enhancements.cpp and it is unchecked by anything automated.

## Known failure modes

(none recorded yet)
