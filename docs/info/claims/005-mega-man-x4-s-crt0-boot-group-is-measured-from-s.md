---
id: C005
kind: claim
status: holds
created: 2026-08-12
tags: boot,crt0,re-01
depends: game/core/game_config.cpp, tools/verify_crt0.py
reconfirmed: 2026-08-20 22:21:54
verified_at: 2026-08-20 22:21:54
---

## Claim

Mega Man X4's crt0 boot group is MEASURED from SLUS_005.61: bss [0x8012F418,0x80175F38) = 0x46B20, stackTopBase 0x800DAF3C (no bias, sp=0x80200000), stackTopBase2 0x8011CB74, heapBase 0x80175F38 (size 0x820C8), gp 0x8012F418, libcInit 0x800EDCDC = BIOS A(39h) InitHeap, gameMain 0x80012024, crt0 0x800DAE8C — and this crt0 has NO heap-size/heap-base globals

## Evidence

Disassembled + symbolically executed the PS-EXE entry function from pc0=0x800DAE8C to its terminating break (43 instructions) over the extracted 1,179,648-byte image, sha1 213733031136d095ca275d6957695aa25011cfa5. Reproduce: 'python3 tools/verify_crt0.py --check' -> exit 0, 'CHECK PASSED: all 13 recorded fields re-derived from these bytes', each field printed with the instruction address behind it. 'python3 tools/verify_crt0.py --selftest --cross ../Tomba2Engine/scratch/bin/tomba2/MAIN.EXE' -> 8/8 (3 positive, 5 negative). The 'no heap globals' half is a measurement over a COMPLETE list, not an absence: the function contains exactly ONE absolute store, 'sw ra,-3048(at)' -> 0x8012F418, printed with its denominator. Independent corroborations: (a) external/mmx4's config/symbols.us.txt names 0x800EDCDC 'InitHeap', matching the thunk decode 'addiu t2,0xA0; jr t2; addiu t1,0x39' = A-table function 0x39; (b) external/mmx4's splat config claimed .bss 0x8012F418 size 0x46B20 and the clear loop derives exactly that, so a reference hypothesis was CONFIRMED rather than pasted; (c) the 0x3E8 bytes where .bss overlaps the sector-padded text tail are all zero in the file (0 nonzero of 1000), so the clear loop destroys no initialised data.

## What would falsify it

tools/verify_crt0.py --check exiting non-zero on the extracted SLUS_005.61 (that is the arbiter, and it prints which field moved). Also falsified if a RUNTIME trace shows sp != 0x80200000 or the heap base != 0x80175F3C at the first InitHeap call — this claim is derived from the STATIC image, and it assumes nothing writes 0x800DAF3C or 0x8011CB74 before crt0 runs. Both lie inside .text, so that assumption is strong but was NOT observed on a running system: there is no port binary yet.

## Re-confirmed 2026-08-12 16:10:58

Re-verified 2026-08-12 by re-running the measurement AND, for the first time, comparing it to what SHIPS: tools/verify_crt0.py --check now parses game/core/game_config.cpp and diffs its kCrt0*/kPsExe* constants against the values derived from SLUS_005.61's bytes in the same run — 16 shipped-vs-measured comparisons agree, 0 disagreements, plus 2 shape facts (stackTopBias=0, libcArgs=a0,a1) that have no GameConfig field. The tool no longer holds its own copy of the table (X4_EXPECT is deleted), so this claim's evidence and the shipped value are now the same bytes read once. Proven RED by sabotage: kCrt0GameMain -> 0x80999999 in the shipping file gives 'CHECK FAILED: 1 disagreement(s) ... measured gameMain = 0x80012024', exit 1 — before this change the identical sabotage of three constants passed both --check and --selftest. LIMITATION of the baseline under this claim: its file is still UNTRACKED, so 'verified_at' is the only anchor; it is now second-precision rather than a date, which is what makes a later same-day commit detectable at all. Once the file is committed the ADD-commit anchor takes over.

## Re-confirmed 2026-08-12 22:58:56

Re-verified 2026-08-12 after psxport 726d10c9 and the stackBias declaration changed game_config.cpp. tools/verify_crt0.py --check re-derives the group from SLUS_005.61's bytes and diffs it against the SHIPPING file: PASSED, 19 shipped-vs-measured comparisons agree, req group '0 zero / 10 filled of 10', and heapSizePtr/heapBasePtr correctly read as '0 = ABSENT, as measured' (no store among the 1 absolute store in the prologue). Independently corroborated by psxport tools/crt0_extract, a different tool sharing no code with verify_crt0.py, which resolves 8 of 8 fields with a COMPLETE prologue and agrees on every one.

## Re-confirmed 2026-08-20 22:21:54

Re-run 2026-08-20: python3 tools/verify_crt0.py --check reports 19 shipped-vs-measured comparisons agree and the measured boot-group values remain unchanged after the nearby RE-06 pad constants were added.
