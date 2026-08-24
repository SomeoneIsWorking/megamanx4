---
id: C017
kind: claim
status: holds
created: 2026-08-22
tags: RE-04,boot,threads
depends: game/core/bios_threads.cpp#Service::change, game/core/x4_runtime.cpp#registerOverrides, tools/verify_threads.py#verify
reconfirmed: 2026-08-24 23:09:50
verified_at: 2026-08-24 23:09:50
---

## Claim

Retail MMX4 now crosses the BIOS-thread handoff faithfully enough to enter task 0x8001D064 through its untouched scheduler

## Evidence

tools/verify_threads.py --check --selftest: 3/3 thunks, 7/7 scheduler/create facts, 3/3 task yields, 5/5 shipping constants plus the exact HLE window, and 6/6 positive/negative controls; mmx4_runtime_test proves distinct TCBs, SP/GP plus register persistence over yield/resume, main preservation, invalid/capacity refusal, deferred self-close while its coroutine is live, and reuse only after the main stack resumes; scratch/logs/re04-bios-thread-runtime-final-ad5cf802.log reaches 0x8001D064 from retail func_80012600 through OpenTh handle 0xFF000001 with zero ABI violations.

## What would falsify it

A rebuilt unforced run with HLE thunk tracing excluded no longer reaches 0x8001D064 through a non-main handle, the verifier fails, or the focused context-switch test loses either preservation/refusal answer.

## Re-confirmed 2026-08-22 17:48:53

2026-08-22: thread evidence check/selftest passes, x4_runtime test passes, and clean-pin real-disc trace re04-bios-thread-runtime-final-ad5cf802.log reaches retail task 0x8001D064 through func_80012600.

## Re-confirmed 2026-08-22 18:10:37

2026-08-22 clean psxport ad5cf802: thread verifier passes 6/6, runtime test passes, and re04-bios-thread-runtime-final-ad5cf802.log reaches 0x8001D064 at frame 5 through OpenTh FF000001 with zero ABI violations.

## Re-confirmed 2026-08-22 18:55:27

2026-08-22 candidate framework rerun: verify_threads passes 6/6, mmx4_runtime_test passes inside full Clang CTest 7/7, and the real-disc trace preserves the retail task path through 0x8001D064 then reaches later task creation 0x800128B8 and entry 0x8001DAF8 with zero ABI violations.

## Re-confirmed 2026-08-24 23:09:50

On commit a53c255, verify_threads.py passed the 3/3 thunks, 7/7 create/scheduler facts, 3/3 yields, 5/5 shipping constants/window, and 6/6 opposite-answer cases. Full Clang CTest passed mmx4_runtime_test, and the clean-pin runtime reached later synchronous front-end disc requests through the unchanged retail thread scheduler.
