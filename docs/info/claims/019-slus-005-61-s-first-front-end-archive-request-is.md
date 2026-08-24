---
id: C019
kind: claim
status: falsified
created: 2026-08-22
tags:
depends: external/psxport/runtime/recomp/cdc_native.cpp#schedule_sector_event, external/psxport/runtime/recomp/timing.cpp#Timing::advanceGuestInstructionTicks
falsified_on: 2026-08-22
---

## Claim

SLUS_005.61's first front-end archive request receives valid sequential position headers, while psxport's instruction-tick CD deadline starves each sector across yielded VSync fields; a separate four-sector retry remains unresolved

## Evidence

Retail table 0x800F1118 gives request 0x40 = LBA222, size 0x18800; scratch/logs/re04-front-end-cd-callback-boundary.log reaches the alternate ready callback and sequential DMA, and scratch/raw/re04-cd-header-f261.ram carries 00:04:73:02 plus expected LBA 0xDF. scratch/logs/re04-cd-instruction-deadlines.log proves +225792 instruction-tick deadlines and also shows the distinct LBA222..225 then restart cycle. scratch/logs/re04-front-end-unpaced-progress.log never reaches 0x8001512C after 35 seconds with host pacing disabled. psxport issue #7 documents physical thresholds on guestInstructionTicks but does not explain the four-sector retry.

## What would falsify it

Falsified if the exact pinned build reaches 0x8001512C within a bounded correctly paced real-disc run without changing the shared CDC time owner, or if a RAM capture shows a bad/non-sequential sector header or expected-LBA comparison.

## FALSIFIED 2026-08-22

The candidate A/B proves the apparent four-sector retry is not a separate unresolved hardware failure: retail func_80014C70 exhausts its 601-iteration timeout because CDC time is instruction-starved, writes 0xC0, and rearms; shared field-aware emulated time prevents the timeout and reaches 0x8001512C.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
