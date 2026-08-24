---
id: I014
kind: instrument
status: trusted
created: 2026-08-24
tags: lens,hermetic,RE-07
depends: game/core/player_object.h, tests/test_x4_player_object.cpp, cmake/megamanx4_port.cmake
---

## Instrument

`game/core/player_object.h` (the RE-07 typed read-only guest-memory lens) as gated by
ctest `x4_player_object` (`tests/test_x4_player_object.cpp`, registered in
cmake/megamanx4_port.cmake).

What it asserts: every named constant/offset in the lens lands on the byte the RE doc says it
does. POSITIVE class — a full identity pattern planted across each measured block is read back
through every accessor with the documented semantics (signed halves, active flag, character,
bg slot, animation, hp). NEGATIVE classes — (1) non-aliasing: plants at +0x100 offsets and at
adjacent camera layers/pad blocks must stay invisible to correctly-addressed lenses; (2)
offset pinning: any wrong offset constant reads a wrong planted value and fails.

## Proven non-vacuous

The FIRST run of this instrument failed for real before it passed: the initial negative check
was written so its answer was masked by leftover positive-phase state (`active` stayed 1 from
the earlier plant), and the test caught it — the negative could not have distinguished aliasing
from residue. The negative was redesigned to clear the real block first; only then did the gate
go green. That failure is the demonstration that the test can report the other answer.

Known blind spots: it validates the LENS against synthetic RAM, not the GAME against real
guest state — "the lens reads what we planted" is not "the game keeps live data there". Live
reachability of these addresses during gameplay is claim C022's runtime-falsifier territory,
and no play-through-style proof ships with this step.
