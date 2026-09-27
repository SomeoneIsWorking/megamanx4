---
id: 30
title: This title has no live-play client, so nothing here was ever asked while the game was RUNNING
status: open
symptom: Every Mega Man X4 product run in this repository is a fixed field budget with no input, and the
  post-movie park has been characterised by sampling guest words at three named presents
tags: instrumentation,input,front-end,falsifier
created: 2026-09-27
updated: 2026-09-27
---

This repository had no live-play client while `docs/project-state.md` records S002 as `missing` and
S009 as `missing`. Both of those rows are statements about a product that is RUNNING and being
watched, and the only product runs this repository could produce were a fixed `PSXPORT_NATIVE_FRAMES`
budget with no input at all. That is a real gap, and it is not the same gap as "the title does not
run":

* the post-movie park in issue 0028 was characterised from presents 15,006 / 20,023 / 23,218 of a
  24,000-present run — three samples, with no statement of how the state behaved BETWEEN them, and no
  statement of whether a pad edge could have been consumed;
* the falsifier issue 0029 needs to be run "after a run", and its own wording separates "the state
  word did not move" from "the owner was never reached". A run that cannot observe the owner's tally
  cannot tell those apart, so the falsifier was unanswerable as the tooling stood;
* no run had ever asked the front end a QUESTION with a pad edge, so "S009 representative gameplay"
  had no instrument behind it at all.

## What was built, and what is deliberately NOT in it

`tools/title_prompts.py` — the front-end model. It owns which guest cells say which state, and the
rule that turns a state into a button. It holds no transport.

`tools/live_play.py` — the transport and the route. It reuses the framework's ONE client for the
live debug server (`external/psxport/tools/dbgclient.py` over `runtime/psx/dbg_server.cpp`), the
framework's ONE headless launch policy (`external/psxport/tools/port/launch_environment.py`), and the
framework's ONE image reader (`external/psxport/tools/port/present_geometry.py`). It writes no second
transport, no second image reader and no second launch policy.

### The screen model is the title's own state machine, not a list of screen names

`func_8001DAF8` (323C.c:1597) is the game task: each iteration it calls
`D_800F21B0[game_info.unk0](&game_info)`, so `game_info.unk0` IS the front-end state and
`game_info.mode` is the sub-state inside it. Sub-state 2 of state 1 is `func_8001DDB0`
(0x8001DDB0), the measured post-movie park. Naming screens by that dispatch is not a model of what
the title looks like; it is the index the title itself dispatches on, read out of the words the title
writes.

### The tap policy is a census decision, and deliberately so

`func_8001E708` (323C.c:1846) reads Start only `if (controller_state & PADstart && arg0->unkD == 1)`,
and `func_8001DAF8` (323C.c:1605) takes a DIFFERENT Start arm only `if (game_info.unkD == 0)`. So
`unkD` is the whole question, and the driver asks it rather than deciding a cadence.

This is not a style choice. The `unkD == 0` arm jumps the front end to game state 5
(`game_info.unk0 = 5; mode = 0; unk2 = 0; unk3 = 0`, 323C.c:1619-1622) with a fade. A blind
Start-masher offered while the state machine is parked would therefore ABANDON the state word the
falsifier reads, and `D_80139530` would still read 6 — for a reason that has nothing to do with
issue 0029. That is exactly the shape the falsifier exists to prevent, and it is why this client
offers a pad edge only where the census says the guest's own code reads one, and prints the `unkD` and
the pad trio beside every tap it offers.

### Input evidence is the guest's own words, at two levels

`game/core/player_object.h:37-39` measured the pad trio: held `0x80166C08`, previous `0x80166C0A`,
pressed `0x80166C0C` — and the pressed word is byte-identical to the decomp's `controller_state`
(`external/mmx4/config/symbols.us.txt:744`), independently. Below that, `game/core/pad_layout.h:16`
publishes the raw libpad packet buffer at `0x80166D68`, whose button word is ACTIVE LOW.

So a run can distinguish three things a fixed-budget run cannot:

1. the edge never reached guest memory (raw word and all three decoded words unchanged),
2. the edge reached the guest and the front end's handler did not read it (`unkD` says so), and
3. the edge was read and nothing acted on it.

Those are three findings. "The screen did not change" is a fourth, weaker thing, and it is reported
beside them rather than instead of them.

## The falsifier, instrumented so it can answer its own negative

Issue 0029's falsifier is: *"If the state word is still 6 with a non-zero `x4-music-cd` tally after a
run, the substituted `CdSync` owner is not the thing that was failing."*

That needs the tally. The tally in `game/core/music_cd.cpp` is a `lucent::debug("x4-music-cd", ...)`
call site, and `lucent::debug` is channel-gated, so **a run with the channel off cannot observe the
owner being reached at all** — and "the state word did not move" would be indistinguishable from "the
owner was never offered the leaf". This client therefore sets `PSXPORT_DEBUG=x4-music-cd` for the
whole run rather than arming the channel over the endpoint mid-route, because the movie phase is
exactly where the state machine first runs and an endpoint-armed channel would leave it unobserved.

`title_prompts.falsifier_verdict` then answers FOUR ways rather than two, because the two-way version
cannot distinguish the interesting negative from an absent measurement:

| the state word left 6 | the owner logged | verdict | what it means |
|---|---|---|---|
| yes | any | `ADVANCED` | the chain moved; the owner is implicated |
| no | a refusal | `REFUSED-BY-OWNER` | the owner's own named outcome (`music_cd.cpp` aborts on it) |
| no | a served `CdSync` edge | **`FALSIFIER FIRES`** | the substituted owner WAS reached and the word still did not move — issue 0029's mechanism is wrong a third time |
| no | nothing | `NOT REACHED` | the leaf was never offered: an absent measurement, NOT evidence against the owner |
| never observed | any | `UNMEASURED` | the probe itself did not answer |

The third row is the one that would retire the mechanism, so it is named as such and is never folded
into a "no progress" reading. The fourth is the one a two-way verdict would have read as the third.

## The picture test, and why it is a colour count

Issue 0028 measured the park's own picture: **2 distinct colours** (`#080810`, `#000000`), with a
798x3 band at y=717 differing by 2,394 of 924,480 pixels between consecutive presents. So:

* the park is NOT frozen — consecutive captures differ — but it is also NOT a scene. A
  frame-to-frame-difference test alone would rate the park as "moving", which is the wrong answer;
* the park's non-black share is 61.89%, because the clear colour is RGB(8,8,16) and not black. A
  non-black test would rate it as "something is on screen";
* at the park the `[wide]` announcement OSCILLATES between `render_width=320` and `render_width=428`,
  1:1 correlated with the guest's own `GP1(08)` display-depth switch (docs/project-state.md S006). A
  capture-difference test therefore sees a large geometric change every capture while nothing is
  animating.

So "a post-movie present contains scene" is judged on the DISTINCT COLOUR COUNT against the park's own
measured 2, and the report prints the count for every capture with its denominator, whether the leg
passed or not.

## The census, and its holes

One poll is six contiguous byte reads, not one command per field, because the endpoint services at
most one command per PRESENTED frame — a census's cost is measured in frames, and this title's history
says to distrust a frame budget (the same boundary was measured at field 974 in one run and 13,153 in
another).

| read | covers |
|---|---|
| `r 80173C70 24` | `game_info` (0x10) **and** the handshake byte at +0x14 |
| `r 80139520 56` | the sticky error, the XA/BGM machine-state word and the published result byte (0x24 apart) |
| `r 80141BD0 16` | music-active and the guest's own field counter |
| `r 801721C0 32` | `engine_obj` stage/substage |
| `r 80166C08 6` | the pad trio |
| `r 801418C8 96` | the player lens, through `game/core/player_object.h` |

`misc_objects` is 0x1800 bytes and the endpoint serves 256 per command, so it is read ONCE at the end
in 24 commands and reported as `populated / records_read` — counting 40 of 96 records would print a
smaller number that reads as "fewer objects", which is the wrong question.

Two hole classes are declared rather than absorbed:

* a read that returns FEWER bytes than asked for RAISES. A silently-short read is how a failed probe
  becomes a confident table, and the framework has already been bitten by exactly this
  (`psxport/AGENTS.md`, "a short answer must declare itself").
* a read that times out on all its retries drops the WHOLE observation and is counted, and the run
  prints the count. A census with silent holes is a census whose gaps a reader cannot see.

## The addresses are checked against their owners, every run

`title_prompts.verify_address_owners` re-reads the declaration in the file that OWNS each address and
compares it to the value this tool reads: `tools/title_prompts.py` itself, `game/core/music_cd.h`,
`game/core/pad_layout.h`, `game/core/player_object.h`. A disagreement — or an owner that stopped
declaring the name — refuses the run before it launches anything. This is the same discipline as
`Tomba2Engine/tools/live_play.py::verify_address_owners`, and the reason it is not a spot check: a
guest address that moved while a tool kept the old one makes the tool drive a stranger's memory while
still printing a confident table.

## Result

<!-- FILLED IN BY THE RUN: see the sections below. -->
