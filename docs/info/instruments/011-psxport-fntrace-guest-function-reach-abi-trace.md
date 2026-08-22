---
id: I011
kind: instrument
status: trusted
created: 2026-08-21
---

## Instrument

PSXPORT_FNTRACE guest-function reach/ABI trace

## Validated by

scratch/logs/re04-postinit-state-trace.log shows both answers in one bounded run: six main-loop functions report 222 calls with zero ABI violations while three downstream CD-read functions report NEVER CALLED. scratch/logs/re04-3418-thread-boundary-trace.log independently shows the created ChangeThread wrapper reached 86 times while its retail entry and first callee remain never-called. Limitation: tracing the CD callbacks changed whether issue #10 reproduced, so FNTRACE is trusted for function reach/count/ABI only and must not be used as a forward-progress or timing discriminator.

## Known failure modes

Tracing a PlatformHle-owned guest thunk (OpenTh/CloseTh/ChangeTh) installs FNTRACE's raw generated
wrapper after the HLE and displaces the handler. `scratch/logs/re04-bios-thread-runtime.log` then
returns the old constant `0xFF000000` and never enters the task. The paired unshadowed trace omits
those three thunk addresses and reaches `0x8001D064` through handle `0xFF000001`. Therefore FNTRACE is
trusted for ordinary guest-function reach/ABI only; never include an HLE-owned thunk in a mechanism
gate. Use the owning subsystem's diagnostic channel for that thunk.
