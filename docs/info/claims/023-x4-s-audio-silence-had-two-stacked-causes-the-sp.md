---
id: C023
kind: claim
status: holds
created: 2026-08-24
tags: audio,spu,RE-11,vsync
depends: game/core/vsync_sync.cpp#deliver_field
---

## Claim

X4's audio silence had two stacked causes: the SPU mixer was never advanced (zero spu_update call sites on the guest-driven path) and libsnd's SS tick never ran because the seam delivered the BOOT class-0 handler instead of the SetInterrupt table's CURRENT occupant (0x800DD7FC chains the old VBlank walk AND the sequencer tick; tick mode is SS_TICKVSYNC, rate global 0x80173C88=0x3C)

## Evidence

BEFORE: PSXPORT_WAV wrote 0 bytes (scratch/logs/audio-before.log). Mixer-advance-only intermediate: 26.4M stereo frames rendered, peak=0, 6 KON writes (scratch/logs/audio-after2.log). AFTER delivering the live class-0 slot: 269,452 KON writes; WAV peak 24574, 42.78% non-zero, RMS 2233 over 15.7M analyzed frames (scratch/raw/audio-tick2.wav, scratch/logs/audio-tick2.log). Registration chain decompiled to C: scratch/decomp/x4_sstick*.c, x4_irq0*.c; live class-4 slot 0x800DB544 and tick globals read from scratch/raw/snap_150.bin

## What would falsify it

a headless PSXPORT_WAV run on the landed build whose WAV has zero non-zero samples while [spudbg] shows KON writes, or a guest that registers its tick OUTSIDE the 0x8011CB98 class-0 slot
