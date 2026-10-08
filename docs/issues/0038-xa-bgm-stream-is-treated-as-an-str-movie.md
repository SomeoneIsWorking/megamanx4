---
id: 38
title: An XA BGM stream is treated as an STR movie
status: open
symptom: 16:9 drops to 4:3 when title music starts, and the frame driver skips the retail draw prefix while BGM plays
tags: widescreen,movie,music,frame-loop
state_items: S004,S006
created: 2026-10-07
updated: 2026-10-07
---

## Reproduction

Record path, `PSXPORT_X4_WIDESCREEN=1`, `PSXPORT_DEBUG=x4-music-cd`, 1,300 presents
(`scratch/record/x169/run.log`): the 15-bit title field is presented 428 wide until the music state
machine issues `CdControl` command `0x1B` (ReadS) at state 1 (`0x80016B58`), between presents 1,290
and 1,295; the next presentation line is `render_width=320` and every later capture is 960x720.

## Cause

psxport `cd_override.cpp` sets `Game::cd.stream_active` on every ReadN/ReadS, BGM included. Two X4
owners read that word as "an STR movie owns the picture":

- `x4::WidescreenPolicy::presentationAspect` (`game/widescreen/widescreen_controller.cpp`) returns
  4:3 while it is set;
- `movieOwnsPicture` (`game/frame/x4_frame_driver.cpp`) skips `runRetailFramePrefix` and
  `runRetailFrameSuffix` while it is set.

## Proper fix

Key movie ownership on X4's own STR owners: a state set by `x4::stream_startup::run` (0x80018788) and
cleared when `x4::movie_cleanup` completes, read by both owners. `cd.stream_active` stays the CD
pump's word.
