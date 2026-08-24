---
id: 21
title: Synchronous archive drain rejected PsyQ VSync counter query
status: resolved
symptom: Real-disc fast loading aborted during request 64 with unexpected VSync in synchronous loader scope
tags: fastwait,loading,vsync,gpu,RE-09
created: 2026-08-24
updated: 2026-08-24
---

## Root cause

Archive postprocess 0x80014780 reaches LoadImage 0x800148EC, then PsyQ set_alarm 0x800ECB38.
set_alarm calls VSync(-1) to read guest counter 0x8011DC50 and stores counter+240 as a GPU timeout.
The scoped loader admitted only issuer setup VSync(3), so it rejected this measured pure query during
Delivering.

## Fix and evidence

During Delivering, fast_wait::vsync now admits exactly UINT32_MAX and super-calls the untouched
generated VSync body. That branch returns the live counter without waiting, advancing a field, or
presenting. Every other unexpected scoped VSync remains fail-closed. The focused production-leaf test
plants a nonzero counter and proves the exact return and unchanged counter/phase. A bounded
uninstrumented real-disc run then completed requests 64, 65, 113, and 51 and remained live until
timeout.

## Falsifier

Any scoped non-query VSync is accepted, VSync(-1) returns a fabricated value or mutates the
counter/phase, or a real archive load again aborts in the set_alarm/get_alarm chain.
