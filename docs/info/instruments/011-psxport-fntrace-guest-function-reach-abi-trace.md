---
id: I011
kind: instrument
status: trusted
created: 2026-08-21
---

## Instrument

PSXPORT_FNTRACE guest-function reach/ABI trace

## Validated by

scratch/logs/re04-postinit-state-trace.log shows both answers in one bounded run: six main-loop functions report 222 calls with zero ABI violations while three downstream CD-read functions report NEVER CALLED. scratch/logs/re04-ce2-thread-boundary-trace.log independently shows the created ChangeThread wrapper reached 140 times while its retail entry and first callee remain never-called. Limitation: tracing the CD callbacks changed whether issue #10 reproduced, so FNTRACE is trusted for function reach/count/ABI only and must not be used as a forward-progress or timing discriminator.

## Known failure modes

(none recorded yet)
