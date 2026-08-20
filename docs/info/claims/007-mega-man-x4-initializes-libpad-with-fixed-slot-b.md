---
id: C007
kind: claim
status: holds
created: 2026-08-20
tags: pad,coop
depends: game/core/game_config.cpp, tools/verify_pad.py
---

## Claim

Mega Man X4 initializes libpad with fixed slot buffers 0x80166D68 and 0x8012F46C, both capacity 0x22; GameConfig binds those two fixed buffers and intentionally declares no pointer table.

## Evidence

Retail SLUS_005.61 SHA-1 213733031136d095ca275d6957695aa25011cfa5: tools/verify_pad.py --check scanned 294400 loaded words, found the sole jal 0x800EE0D0 at 0x80012194, derived a0..a3 = 0x80166D68,0x22,0x8012F46C,0x22, and matched the shipping GameConfig 4/4. --selftest passed 4/4 positive/negative cases.

## What would falsify it

Falsified if this executable identity changes, a complete instruction scan finds a different InitPAD call count/arguments, runtime observation shows InitPAD receives different buffers, or psxport removes/changes fixed-buffer fallback semantics.
