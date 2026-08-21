---
id: I010
kind: instrument
status: trusted
created: 2026-08-21
---

## Instrument

tools/verify_cd_irq.py

## Validated by

Trusted for the retail interrupt-element, HookEntryInt continuation, trapIntr table, CD callback, result-state, and shipping reentry-seed contract. Positive retail SHA-1 check covers six groups; five in-memory/shipping negative controls change the IRQ verifier bit, remove the trapIntr jal, remove or duplicate the main_reentry seed, and change the CD callback slot, and all are refused. Blind spot: it statically proves the retail/shipping contract but does not itself execute IRQ delivery; the FNTRACE/I_STAT runtime is separate evidence.

## Known failure modes

(none recorded yet)
