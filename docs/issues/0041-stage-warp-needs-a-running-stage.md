---
id: 41
title: The stage warp is legal only once a stage is running, so reaching it still needs front-end input
status: open
symptom: `warp <stage>` refuses at the title and in player select; a run must tap Start through the title, player select and the opening movie before the warp is accepted
tags: debug,warp,front-end
state_items: S012
created: 2026-10-15
updated: 2026-10-15
---

## Reproduction

Hidden window, `aspect=0`, `ires=1`, control channel on. `warp 3` at the title answers
`refused: a warp is legal only while a stage is running`. After Start taps reach the intro stage
(engine state 6, sub-state 0), the same command is armed and Split Mushroom is reached
(`scratch/restructure/warp/warp.log`).

## Cause

`game/debug/stage_warp.cpp:StageWarp::arm` accepts only engine state 6 sub-state 0, because the warp
enters through state 4 (loader `0x80013014`), which loads the stage archives but not the per-character
archive. That archive is loaded once, by player select's last state (`character_select_state_6`,
`0x80012EB8`), which then sets engine state 3 with stage 0 (the opening movie and Hunter H.Q.).

## Proper fix

Let `StageWarp` arm in engine state 1 (player select) as well: at the frame boundary, take player
select through its own exit (`character_select_state_5` fade, then `character_select_state_6`, which
loads the character archive and sets state 3), and when state 3 sub-state 0 is entered with a warp
pending, write the stage and part and set state 4 as the in-stage warp does. What engine state 3
initializes before its first stage load (sub-states 0-11, `external/mmx4/src/main/1A5BC.c`,
`1FD10.c`) must be read first, so the state-4 entry starts from the same player and engine state. The
title runs before the engine loop and still needs its own route into engine state 0.
