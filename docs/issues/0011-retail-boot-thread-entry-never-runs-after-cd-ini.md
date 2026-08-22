---
id: 11
title: Retail boot thread entry never runs after CD initialization
status: resolved
symptom: MMX4 presents paced black frames after Setmode; no archive/read command occurs and thread entry 0x8001D064 is never called even though ChangeThread runs every frame
tags: boot,thread,bios,libcd,RE-04,next-boundary,framework
created: 2026-08-21
updated: 2026-08-22
---

Retail call flow creates task 0 with entry 0x8001D064 through func_80012740, then func_80012600 calls ChangeThread with handle 0xFF000000. The entry sets the main-state enable at 0x8013BD44 and begins front-end initialization. Upstream Mednafen PC coverage includes 0x8001D064, but no locally installed true-oracle executable is available to capture fresh ordered state; that coverage is only corroboration, not result-state evidence.

Live evidence: scratch/logs/re04-3418-thread-boundary-trace.log against exact framework pin 3418a79b records func_80012740(a0=0,a1=0x8001D064), then 86 calls to ChangeThread wrapper 0x800EDDBC from ra=0x800126AC over 3 seconds, while 0x8001D064 and its first state callee 0x800128B8 are NEVER CALLED. The shared framework runtime/recomp/threads.cpp explicitly implements B0:0x0E OpenThread as a constant 0xFF000000 handle and B0:0x10 ChangeThread as a no-op. Therefore the post-CD game thread cannot start.

This is a shared BIOS execution-model boundary, not a reason for a game-local direct dispatch: direct-calling 0x8001D064 would skip the retail cooperative scheduling contract and become a polling/thread bypass. Coordinate a psxport design and cross-consumer test before editing the framework.

### Note (2026-08-22)
2026-08-22 follow-up: the in-flight game-local tasks.cpp bypass installed and the build ran, but a bounded FNTRACE still reported 0x8001D064 NEVER CALLED while func_80012600 ran 40,431 times. The bypass therefore does not cross the recorded scheduler boundary and is not rendering evidence. Separately, the executable now selects the guest GTE path by title policy; native is refused because X4 has no native producers. Black remains an upstream thread/scheduler boundary, not a renderer-selection excuse.

### Note (2026-08-22)
A second diagnostic exposed another failure mode in the in-flight tasks.cpp bypass. A scripted REPL run without FNTRACE logged x4_task_restart, opened the disc, then remained stuck in the guest VSync chain under gen_func_8001DCCC and produced no requested screenshot. Repeating with FNTRACE for 20 seconds reported 0x8001D064 and 0x8001DCCC never called while func_80012600 ran 136,263 times. Therefore the bypass is driver/instrument-sensitive and cannot be treated as a faithful scheduling implementation; neither leg rendered a non-black frame. Do not collapse this into the stronger claim that no downstream task-shaped code can ever execute.

### Note (2026-08-22)
Audit of the discarded synchronous-CD attempt: filling GameConfig cdInit/cdCommand/cdSync/cdGetSector/callback-state fields would register psxport PlatformHle replacements over X4's already-verified retail controller -> IRQ2 -> libcd callback path. The accompanying shared CdReady body and stock-read loop edits only compensated for activating that wrong path; none implements ChangeThread or schedules task 0x8001D064. The game fields and shared edits were removed. Keep CD HLE zero until loading-removal RE identifies a file-I/O seam downstream of the faithful interrupt path.

### Resolution (2026-08-22)
Root cause was the missing BIOS TCB execution contract under the untouched retail scheduler, not CD or rendering. X4Runtime now creates a per-Core service: OpenTh allocates one of the three non-main SYSTEM.CNF TCBs and captures entry/SP/GP, ChangeTh strict-ping-pongs main and task fibers while preserving registers/C stacks, and CloseTh releases the handle. A self-closing task defers actual TCB reuse until ChangeTh has regained the main C stack; otherwise OpenTh could destroy the coroutine still executing CloseTh. tools/verify_threads.py passes a real positive plus five mutations; mmx4_runtime_test proves yield/resume, deferred self-close, and refusal controls; the final unshadowed real-disc trace reaches 0x8001D064 through retail func_80012740 -> OpenTh 0xFF000001 -> func_80012600 -> ChangeTh. The next boundary is inside the front-end task before 0x800128B8, not the resolved scheduler handoff.
