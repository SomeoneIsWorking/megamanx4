---
id: 11
title: Retail boot thread entry never runs after CD initialization
status: investigating
symptom: MMX4 presents paced black frames after Setmode; no archive/read command occurs and thread entry 0x8001D064 is never called even though ChangeThread runs every frame
tags: boot,thread,bios,libcd,RE-04,next-boundary,framework
created: 2026-08-21
updated: 2026-08-21
---

Retail call flow creates task 0 with entry 0x8001D064 through func_80012740, then func_80012600 calls ChangeThread with handle 0xFF000000. The entry sets the main-state enable at 0x8013BD44 and begins front-end initialization. Upstream Mednafen PC coverage includes 0x8001D064, but no locally installed true-oracle executable is available to capture fresh ordered state; that coverage is only corroboration, not result-state evidence.

Live evidence: scratch/logs/re04-ce2-thread-boundary-trace.log against exact framework pin ce2c83ad records func_80012740(a0=0,a1=0x8001D064), then 140 calls to ChangeThread wrapper 0x800EDDBC from ra=0x800126AC over 3 seconds, while 0x8001D064 and its first state callee 0x800128B8 are NEVER CALLED. The shared framework runtime/recomp/threads.cpp explicitly implements B0:0x0E OpenThread as a constant 0xFF000000 handle and B0:0x10 ChangeThread as a no-op. Therefore the post-CD game thread cannot start.

This is a shared BIOS execution-model boundary, not a reason for a game-local direct dispatch: direct-calling 0x8001D064 would skip the retail cooperative scheduling contract and become a polling/thread bypass. Coordinate a psxport design and cross-consumer test before editing the framework.
