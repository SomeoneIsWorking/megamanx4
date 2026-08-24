---
id: C007
kind: claim
status: holds
created: 2026-08-20
tags: pad,coop
depends: game/core/game_config.cpp, tools/verify_pad.py
reconfirmed: 2026-08-24 23:09:44
verified_at: 2026-08-24 23:09:44
---

## Claim

Mega Man X4 initializes libpad with fixed slot buffers 0x80166D68 and 0x8012F46C, both capacity 0x22; GameConfig binds those two fixed buffers and intentionally declares no pointer table.

## Evidence

Retail SLUS_005.61 SHA-1 213733031136d095ca275d6957695aa25011cfa5: tools/verify_pad.py --check scanned 294400 loaded words, found the sole jal 0x800EE0D0 at 0x80012194, derived a0..a3 = 0x80166D68,0x22,0x8012F46C,0x22, and matched the shipping GameConfig 4/4. --selftest passed 4/4 positive/negative cases.

## What would falsify it

Falsified if this executable identity changes, a complete instruction scan finds a different InitPAD call count/arguments, runtime observation shows InitPAD receives different buffers, or psxport removes/changes fixed-buffer fallback semantics.

## Re-confirmed 2026-08-21 02:50:21

2026-08-21: verify_pad.py --check scanned 294,400 words, found the unique InitPAD call and matched 4/4 shipping arguments; --selftest 4/4

## Re-confirmed 2026-08-21 03:15:01

2026-08-21 post-landing verify_pad.py --check: unique InitPAD call at 0x80012194; 4/4 shipping arguments match fixed buffers 0x80166D68 and 0x8012F46C with size 0x22

## Re-confirmed 2026-08-21

Post-landing verify_pad found the unique retail InitPAD call and matched all four fixed-buffer arguments 4/4.

## Re-confirmed 2026-08-22 15:30:37

Ran `tools/verify_pad.py --check` and `--selftest` separately after the X4Runtime render-policy
change; the one retail InitPAD call, both fixed buffers/capacities, shipping bindings, and all 4
positive/negative cases still pass.

## Re-confirmed 2026-08-22 18:55:26

2026-08-22 candidate framework rerun: verify_pad scans 294,400 retail words, finds the unique InitPAD call, matches 4/4 fixed-buffer arguments, and passes 4/4 positive/negative controls.

## Re-confirmed 2026-08-24 23:09:44

On commit a53c255, verify_pad.py --check scanned all 294,400 loaded words, found exactly one InitPAD call, and matched the four shipping arguments 0x80166D68/0x22/0x8012F46C/0x22. Its independent selftest passed 4/4 including changed immediate, unwired config, and removed-call negatives.
