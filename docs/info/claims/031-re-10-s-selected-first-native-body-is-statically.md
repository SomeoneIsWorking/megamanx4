---
id: C031
kind: claim
status: holds
created: 2026-08-26
tags:
depends: game/core/x4_runtime.cpp#X4Runtime::registerOverrides, game/core/title_quad.cpp#initializeWhiteLogoQuad
---

## Claim

RE-10's selected first native body is statically bound to the retail title state-0 white-logo initializer and passes its hermetic object/register contract

## Evidence

tools/re_title_quad.py on SHA-1 213733031136d095ca275d6957695aa25011cfa5 reuses the title path, proves 0x8010FDD0[0] -> 0x800D6F94, matches all 49 retail instructions, diffs 17 shipping facts and the retained-super triple, and rejects three mutations; x4_title_quad passes 23 checks; Clang product link and CTest 13/13 pass against clean psxport dbdb2baf. An exact-pin real-disc run reaches the body and reports mirror equality. Its sampled presents were a stable dark title field, so visible composition is explicitly outside this claim. The claim remains narrower than full live-instrument trust because no deliberate live mismatch has yet been observed.

## What would falsify it

Falsified if the retail body/dispatch changes, the shipping source gate or hermetic contract fails, or a live mirror run shows that the selected native body is not equivalent.
