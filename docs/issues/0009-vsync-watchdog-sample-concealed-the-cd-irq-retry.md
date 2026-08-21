---
id: 9
title: VSync watchdog sample concealed the CD IRQ retry loop
status: investigating
symptom: Boot watchdog repeatedly samples 0x800E4DB0 in the 0x800E5ACC to 0x800E6E14 chain and appears to show a VSync stall.
tags: boot,cd,irq,vsync,RE-04,RE-11
created: 2026-08-21
updated: 2026-08-21
---

Retail disassembly proves 0x800E4DB0 is libetc VSync and the observed CD command body calls it with mode -1 only to read a 960-field deadline. A focused runtime after installing the independently measured VBlank wait route never enters the blocking helper. It repeatedly issues CD commands 0x01 and 0x0A; the native controller raises IRQ2 and I_STAT becomes 0x004 with mask 0x00D, but the one registered BIOS interrupt element reports that it did not claim the source. Therefore the old watchdog stack was a hot-loop sample, not proof that VBlank waiting was the current blocker. RE-11 remains partial until a blocking VSync exercises its helper; the live boot blocker moves to RE-04's CD interrupt/callback contract. Do not add a synchronous CdInit success override from this trace: the controller is already producing responses, and bypassing the unclassified guest IRQ path would hide the real contract.

### Note (2026-08-21)
Final rebuilt runtime (scratch/logs/re11-final-runtime.log): installs the exact helper, reaches guest main, repeats commands 0x01/0x0A with IRQ2 latched/unmasked, and watchdog samples 0x800E6E14 -> 0x800E74DC -> 0x800E5C14 -> 0x800E5ACC. No x4-vsync field line appears, proving the blocking helper was not entered on this path.
