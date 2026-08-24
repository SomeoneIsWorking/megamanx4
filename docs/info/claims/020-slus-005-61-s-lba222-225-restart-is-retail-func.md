---
id: C020
kind: claim
status: holds
created: 2026-08-22
tags: boot,cdrom,timing
depends: game/core/vsync_sync.cpp#deliver_field, psxport.pin
reconfirmed: 2026-08-22 18:58:29
verified_at: 2026-08-22 18:58:29
---

## Claim

SLUS_005.61's LBA222..225 restart is retail func_80014C70's 601-iteration timeout caused by the shared sparse instruction clock, not a separate archive-decode or DMA-framing failure

## Evidence

scratch/logs/re04-baseline-state-watch.log attributes D_801406AC=0xC0 to 0x800E4DB0 at retail RA 0x80014D64 after LBA224; exact generated retail control flow shows that call follows func_80014C70's 601-iteration budget. Extracted LOAD_U.ARC bytes 2048..4095 exactly match all 2048 bytes delivered at guest RAM 0x8012F4B4. Against the shared field-aware emulated-time candidate, scratch/logs/re04-cdtime-candidate.log services LBA225 onward and reaches 0x8001512C frame67, PlayCapcomLogo, and task 0x8001DAF8 with zero traced ABI violations and no first-request 0xC0 timeout.

## What would falsify it

Falsified if a correctly field-timed shared controller still enters the 0x80014D64 timeout path for request 0x40, if retail disassembly shows the 601-iteration attribution is wrong, or if a repeat RAM/disc comparison disagrees.

## Re-confirmed 2026-08-22 18:54:57

The tracked X4 wait seam and recorded psxport pin are the consumer/configuration this A/B rests on. scratch/logs/re04-baseline-state-watch.log attributes D_801406AC=0xC0 to 0x800E4DB0 at retail RA 0x80014D64 after LBA224; retail generated control flow gives the 601-iteration budget. The shared candidate reaches 0x8001512C, PlayCapcomLogo, and task 0x8001DAF8; the extracted LBA223 payload matches all 2048 guest bytes.

## Re-confirmed 2026-08-22 18:58:29

The tracked X4 wait seam and recorded psxport pin are the A/B consumer/configuration. Baseline scratch/logs/re04-baseline-state-watch.log attributes D_801406AC=0xC0 to 0x800E4DB0 at retail RA 0x80014D64 after LBA224; retail control flow gives the 601-iteration budget. Extracted LOAD_U.ARC LBA223 matches all 2048 guest bytes. Candidate unpaced and normally paced logs both reach 0x8001512C frame67, PlayCapcomLogo, and task 0x8001DAF8 with zero ABI violations; paced final-present captures at frames 800/1000 are coherent and 49.27%/50.31% non-black.
