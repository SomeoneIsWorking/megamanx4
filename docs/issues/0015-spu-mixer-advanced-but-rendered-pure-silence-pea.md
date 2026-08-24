---
id: 15
title: SPU mixer advanced but rendered pure silence (peak=0 over 26M frames)
status: resolved
symptom: game has no audio; WAV capture silent; mixer runs; no key-ons after boot
tags: audio,spu,libsnd,vsync,framework
created: 2026-08-24
updated: 2026-08-24
---

## Root cause (two layers)

1. spu_update()/SpuAudio::frame() had ZERO call sites on X4's guest-driven path (X4Runtime::bootInit dispatches guest gameMain and never returns, so Tomba!2's PC-driven per-frame audio hook never runs). Fixed: x4::vsync::deliver_field advances spu_audio.frame() (frameLogic under SBS) once per delivered field.

2. With the mixer advancing, output was STILL silent: libsnd's SS tick never ran. SsStart replaces the SetInterrupt class-0 slot (0x8011CB98) with 0x800DD7FC, which chains the previous VBlank handler AND the sequencer tick; the seam was hardcoded to the BOOT handler 0x800E56FC and so silently dropped everything chained after it. Tick mode is SS_TICKVSYNC at runtime (SsSetTickMode(1) downgraded because the timer query returned 0; rate global 0x80173C88=0x3C). Fixed: deliver the class-0 slot's CURRENT occupant.

## Evidence
BEFORE WAV 0 bytes; intermediate 26.4M frames peak=0 / 6 KONs; after 269,452 KONs, WAV peak 24574, 42.78% non-zero, RMS 2233 (scratch/logs/audio-{before,after2,tick2}.log, scratch/raw/audio-tick2.wav). Claims C023.
