# The three enhancements — design of record, at the level the evidence supports and no further

**MEASURED vs ASSUMED, up front, because at bootstrap time almost everything here is assumed.** What is
measured about this game is a short list: the executable's identity and PS-EXE header, `SYSTEM.CNF`, the
disc's file inventory, that there are no code overlays, the two InitPAD buffers, and that per-character
data is split per file. Nothing about the player object, the camera, the projection site, the game-side
input route or the game's timers has been measured. **Every design statement below that is not tagged MEASURED is a design intention, and
several of them stop mid-sentence on purpose.** A plan that names a fake offset is worse than a plan that
says "unknown".

USER decision, 2026-08-12, verbatim, which is why this file exists at all:

> "Mega Man doesn't need native producers or lerp or native depth, it's already 60fps. It just needs
> widescreen patches (still hard work) and loading removals (again hard work). And I want to add co-op
> to it, drop-in, if I'm playing with X for example then second player can spawn as Zero."

All three are the framework's `pc_enh` class with `affect: full` — they deliberately change canon guest
state — and all three are read through the single chokepoint `x4::enh()`
(`game/core/enhancements.{h,cpp}`), which force-suppresses them under `PSXPORT_ORACLE`, `PSXPORT_SBS` and
a non-empty `PSXPORT_SBS_MODE`. That is what keeps byte-compares enhancement-free *by construction*
rather than by per-call-site discipline. Knob table: `docs/config.md`. Ledger and gate:
`docs/behavior-map.md` + `tools/behavior.py check`.

---

## 1. Widescreen

**What it changes.** A wider-than-4:3 field of view — genuinely more of the world visible, not a
stretched present.

**Follow the framework's model, do not reinvent it.** psxport already has an `aspect` selector
(0 = Vanilla 4:3, 1 = 16:9, 2 = 21:9, 3 = Auto) and it is a real FOV widening: the engine shifts the
projection centre OFX to `nw/2` rather than scaling the framebuffer, and it is forced OFF under
`PSXPORT_ORACLE` and in the SBS legs. Read that first.

**THE SINGLE MOST IMPORTANT SENTENCE IN THIS FILE — the reclassification.** psxport's widescreen is
`affect: none`: a host-side, read-only overlay driven by a NATIVE renderer, and the standing framework
rule is that the picture comes from GAME STATE, never from what the GTE produced. **X4 has no native
renderer** — the guest draws, on the substrate — so a widescreen change here has nowhere to live except
the **guest's own projection setup**. That makes it `affect: full`, which is why it is a suppressed
`pc_enh` and not a render overlay. Misfiling it as `affect: none` would skip both the suppression
requirement and `behavior.py check`'s only real assertion.

**Measured projection contract.** `tools/verify_projection.py --check` scans all 294,400 loaded retail
words and finds exactly six writes to GTE CR24/25/26, all inside `InitGeom`, `SetGeomOffset`, and
`SetGeomScreen`; those routines are each called exactly once from `func_8001213C`. The final state is
OFX=160, OFY=120, H=512. There is no later scene, camera, HUD, or inline raw writer in the resident
executable, so X4 has one global projection setup rather than several pass-specific ones.

**Open, and deliberately not guessed:** the correct host/guest contract for widening that one setup.
X4's required faithful picture path is `gte`, because it has no native producers, while psxport
currently permits wide presentation only on `native`. Retail boot scheduling must work before real
wide pixels and crop-edge asset seams can be verified. Do not resolve either gap with a present
stretch, a forced-native path, or a local renderer exception.

**Suppression.** `x4::enh(x4::cv_widescreen)`; `PSXPORT_X4_WIDESCREEN`.

---

## 2. Loading removals — TWO JOBS, separated before either is estimated

Conflating these is the failure mode. Do not quote one "load time" number for both.

### Job A — raw I/O latency: ALREADY LARGELY GONE BY CONSTRUCTION

psxport converts CD/file I/O to PC-native **synchronous** access under its FAIL-FAST rule. There is no
seek, no 2x-speed sector pacing, no async completion to wait on. **There is nothing to build here; there
is something to measure.** MEASURED support for the *shape* of that measurement: the boot exe holds a
161-entry literal path table (138 ARC + 11 STR + 11 XA + the build's own EXE) at file offset `0xDED4E`,
and its 138 ARC names match the disc's 138 ARC files exactly in both directions — so the complete asset
manifest is already in the binary, which is a ready-made index if a prefetch design is ever wanted.

Caveat, stated because it is arithmetic and not a measurement: `PL00_U.ARC` is 796,672 B and only
~565 KB of RAM remains after `.text` + `.bss`, so `.ARC` files are presumably parsed or streamed in
pieces rather than loaded whole. **HYPOTHESIS.** `RE-04` confirms or kills it, and the answer changes what
"the load is fast" even means.

### Job B — the game's OWN scripted wait states, fade ramps and frame-count timers

No amount of I/O speed touches these: a fade that takes 30 frames takes 30 frames. Collapsing them is a
guest-state change — `pc_enh`, `affect: full` — and it needs `RE-09`. Nothing is located.

**Open:** which waits are safe to collapse at all. A wait that exists to mask a load is free to shorten
once the load is instant; a wait the game's own state machine counts on (an animation whose end triggers
a transition) is not, and telling them apart is the actual work. This plan does not pretend to know
which is which.

**Suppression.** `x4::enh(x4::cv_fastwait)`; `PSXPORT_X4_FASTWAIT`.

---

## 3. Drop-in co-op — and this design STOPS where the player-object layout stops

> "And I want to add co-op to it, drop-in, if I'm playing with X for example then second player can
> spawn as Zero."

**What it changes.** A second player joins mid-play and controls the other hunter.

**The engine assumptions it breaks** — expected, not verified: **one player struct, one camera, one input
route**. A single-player engine typically holds the player as a singleton (a fixed address or slot 0 of
an object table), points the camera at it unconditionally, and routes pad slot 0 into it directly. Each
of those is a separate piece of RE and a separate design decision.

**So the RE target is the PLAYER-OBJECT SYSTEM (`RE-07`), not the renderer.** This is the step the whole
port turns on, and it is the most invasive `pc_enh` in the workspace.

**THE ONE PIECE OF GOOD NEWS THAT IS MEASURED.** The framework already reads two pad slots —
`external/psxport/runtime/recomp/pad_input.cpp:550`:

```cpp
uint32_t bufs[2] = { c->cfg->padSlot0Buf, c->cfg->padSlot1Buf };
```

RE-06 has now landed those fixed buffers from the retail InitPAD call: slot 0 `0x80166D68`, slot 1
`0x8012F46C`, both capacity `0x22`. So co-op's **host input destination exists**. **Do not read a
working second pad as co-op being close** — the game-side route and player-object half are supported by
nothing.

**A LEAD, not a finding.** Per-character data is already split per file on the disc: `PL00_U.ARC` /
`PL01_U.ARC` / `PL02_U.ARC` (796,672 / 741,376 / 796,672 B) for the three playable characters, plus `_X`
and `_Z` variants of the per-stage collision and stage archives (`COL0B_0X` vs `COL0B_0Z`, `ST0B_0X` vs
`ST0B_0Z`). That is a hint the engine already parameterises by character, which would make "spawn the
other hunter" cheaper than it sounds. **It was not verified in code, and it is not evidence that two
player objects can coexist** — per-character *data* files are equally consistent with an engine that
loads exactly one character's set per session, which the `_X`/`_Z` STAGE variants arguably suggest.

### THE DESIGN STOPS HERE, AND SAYS SO

Everything past this point depends on the player-object layout, which is **unknown**. Not "to be
confirmed" — unknown. This document does not name a struct, a field offset, a spawn function, an object
table stride, or a camera-target pointer, because it does not have one and inventing one would make a
broken plan look finished. The questions `RE-07` must answer, in order, are:

1. Is the player a singleton or an entry in a general object table? If a table, is there a free slot?
2. Who owns the camera, and does it take a target pointer or hardcode the player?
3. Where does pad slot 0's state enter the player's update, and is that route parameterised?
4. What is the spawn path for a player, and can it run mid-stage rather than only at stage load?
5. Which per-character state is in the struct vs in globals? Globals are where a second player breaks.

Only after those does it become meaningful to design a drop-in flow.

### The verification consequence, stated explicitly rather than glossed

**With co-op ON the run is not byte-comparable to the oracle by design.** A clean SBS compare with co-op
ON means *the suppression fired*, not that co-op is correct — that is a third fake-green trap on top of
the two the framework's porting doc already names. Therefore:

- the SBS gate runs with **all enhancements OFF**, and that is what `x4::enh()` guarantees;
- **the co-op path needs its own evidence, and what that evidence is, is an OPEN QUESTION (❓).** It is
  not a differential byte-compare, because there is nothing to compare against. It is probably some
  combination of "single-player play with co-op compiled in but off is still byte-exact" (which the SBS
  gate gives for free) plus a behavioural assertion on the co-op path that nobody has designed yet.
  **This file will not invent that gate.** Design it when RE-07 has made it designable, and record it
  here and in `docs/behavior-map.md` when it exists.

**Suppression.** `x4::enh(x4::cv_coop)`; `PSXPORT_X4_COOP`.
