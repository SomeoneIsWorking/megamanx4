---
id: 21
title: Synchronous archive drain rejected PsyQ VSync counter query
status: resolved
symptom: Real-disc fast loading aborted during request 64 with unexpected VSync in synchronous loader scope
tags: fastwait,loading,vsync,gpu,RE-09
created: 2026-08-24
updated: 2026-08-27
---

## Root cause

Archive postprocess 0x80014780 reaches LoadImage 0x800148EC, then PsyQ set_alarm 0x800ECB38.
set_alarm calls VSync(-1) to read guest counter 0x8011DC50 and stores counter+240 as a GPU timeout.
The scoped loader admitted only issuer setup VSync(3), so it rejected this measured pure query during
Delivering.

## Superseded resolution

The former resolution admitted exactly UINT32_MAX during Delivering and called the untouched original
original VSync guest body. That branch returns the live counter without waiting, advancing a field, or
presenting. Every other unexpected scoped VSync remains fail-closed. The focused production-leaf test
plants a nonzero counter and proves the exact return and unchanged counter/phase. A bounded
uninstrumented real-disc run then completed requests 64, 65, 113, and 51 and remained live until
timeout.

That exception is intentionally removed by native frame ownership: full VSync now traps every mode.
`gpu_timeout.*` is the root fix: the retained-super override for set_alarm `0x800ECB38` transcribes
the retail negative-query register/stack/tick path but reads the title's owned field counter at
`0x8011DC50` directly, stores counter+240 at `0x8011E2A0`, and clears `0x8011E2A4`. No guest VSync
entry is dispatched.

The focused Clang test plants counter 317 and proves deadline 557, poll-count zero, restored
callee-saved state, and the exact 39 non-VSync guest ticks. With the full VSync trap armed, real-disc
runs then completed archive request 64 (LBA 222, 100352 bytes, 49 sectors) and direct request 65 (LBA
271, 11420 bytes, 6 sectors). Later aborts moved to independently owned display/XA startup callers,
so the original archive-drain counter-query defect is resolved rather than hidden.

## Falsifier

The set_alarm/get_alarm chain no longer calls guest VSync, consumes a measured direct native clock,
and a bounded archive load completes with the full VSync trap armed.
