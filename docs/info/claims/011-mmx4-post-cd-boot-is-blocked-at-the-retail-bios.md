---
id: C011
kind: claim
status: holds
created: 2026-08-21
tags: RE-04,boot,threads
depends: psxport.pin
reconfirmed: 2026-08-21
verified_at: 2026-08-21 14:15:00
---

## Claim

MMX4 post-CD boot is blocked at the retail BIOS-thread handoff: task entry 0x8001D064 is created, but psxport B0:0x10 ChangeThread is a no-op and never dispatches it.

## Evidence

Retail bytes/generator show func_80012740 receives entry 0x8001D064 and func_80012600 invokes ChangeThread at return address 0x800126AC. scratch/logs/re04-3418-thread-boundary-trace.log, built against exact framework pin 3418a79b, records the create call and 86 ChangeThread calls, while both 0x8001D064 and 0x800128B8 remain NEVER CALLED. external/psxport/runtime/recomp/threads.cpp states and implements thread_change as a no-op. Upstream Mednafen PC coverage contains 0x8001D064 but is not used as ordered/state evidence because no fresh true-oracle executable is installed.

## What would falsify it

Falsified if a rebuilt unforced runtime reaches 0x8001D064 through the retail ChangeThread path, or if retail control flow no longer makes 0x8001D064 the task-0 entry.

## Re-confirmed 2026-08-21 13:14:32

Exact pin ce2c83ad focused reach probe scratch/logs/re04-ce2-thread-boundary-trace.log records task entry 0x8001D064 created and 140 ChangeThread calls from RA 0x800126AC, while 0x8001D064 and 0x800128B8 remain never called; the same shared threads.cpp still implements ChangeThread as a no-op.

## Re-confirmed 2026-08-21

Post-landing ce2c83ad focused trace created task entry 0x8001D064 and observed 140 ChangeThread calls while the entry and 0x800128B8 remained unreached.

## Re-confirmed 2026-08-21 14:13:43

Exact pin 3418a79b focused reach probe scratch/logs/re04-3418-thread-boundary-trace.log records task entry 0x8001D064 created and 86 ChangeThread calls from RA 0x800126AC, while 0x8001D064 and 0x800128B8 remain never called; shared threads.cpp still implements ChangeThread as a no-op.

## Re-confirmed 2026-08-21

Post-landing focused trace created task 0x8001D064 once and observed 86 ChangeThread calls while task entry and 0x800128B8 remained unreached against psxport 3418a79b.
