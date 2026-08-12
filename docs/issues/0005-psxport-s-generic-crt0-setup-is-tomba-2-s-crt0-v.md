---
id: 5
title: psxport's 'generic' crt0_setup is Tomba!2's crt0 verbatim — it blocks X4's RE-01 and has a latent a1 bug against Tomba!2 itself
status: open
symptom: A second consumer's crt0 boot group cannot be written into GameConfig even though every value is measured: two of the eleven fields (heapSizePtr, heapBasePtr) name globals the new game's crt0 does not have, so there is no address that is not a lie. If they are left 0, native_boot.cpp:226/228 write the heap size and base to guest address 0x00000000; if the group is written anyway, sp comes out 8 bytes low and InitHeap gets a garbage size in a1.
tags: framework,boot,crt0,residence-defect,re-01
created: 2026-08-12
updated: 2026-08-12
---

## What happened

RE-01 for Mega Man X4 (SLUS_005.61) completed the reverse engineering — the entry function at pc0=0x800DAE8C was disassembled and symbolically executed to its terminating `break`, and every field of psxport's crt0 boot group was derived from the bytes with a per-field citation (`python3 tools/verify_crt0.py --check`, which diffs the constants `game/core/game_config.cpp` SHIPS against the bytes — 17 comparisons — and `--selftest` gating both classes 14/14). The step still could NOT be closed, because the framework cannot run the crt0 it describes.

## Root cause

`external/psxport/runtime/recomp/native_boot.cpp:218` `crt0_setup` is a faithful transcription of **Tomba!2's** crt0 wearing generic clothes. This was measured, not inferred from reading the C: the same extractor was run over both executables, and over Tomba!2's MAIN.EXE it re-derived all 12 boot-group values that `Tomba2Engine/game/core/game_config.cpp` recorded independently by hand.

Six of ten steps generalize to X4 (bss-clear semantics, stack top from a memory word, the 0x1FFFFFFF heap mask, the heap-size arithmetic, gp/sp/fp, `a0 = maskedHeapBase|0x80000000 + 4`). Four do not:

| # | framework | Tomba!2 | Mega Man X4 |
|---|---|---|---|
| 1 | line 221 hardcodes `mem_r32(cfg->stackTopBase) - 8` | `addi v0,v0,-8` @0x80089710 — really there | **no bias instruction at all**; sp would be 0x801FFFF8 instead of 0x80200000 |
| 2 | line 226 `mem_w32(cfg->heapSizePtr, heapsz)`, unconditional | `sw a1,-16648(at)` -> 0x800ABEF8 | **stores it nowhere** (the function has exactly ONE absolute store, `sw ra` -> 0x8012F418); field 0 => a write to guest 0x00000000 |
| 3 | line 228 `mem_w32(cfg->heapBasePtr, a0)`, unconditional | `sw a0,-16652(at)` -> 0x800ABEF4 | **stores it nowhere**; field 0 => a second write to guest 0x00000000 |
| 4 | sets only `c->r[4]` before `rec_dispatch(c, cfg->libcInit)` | a1 = heapsz live @0x80089738 | a1 = heapsz live @0x800DAEF8 |

**Item 4 is a bug against the existing consumer too, not just a portability gap.** Both games' `libcInit` is the same BIOS thunk shape — `addiu t2,0xA0; jr t2; addiu t1,0x39` = A-table function 0x39, `InitHeap(ptr, size)` (X4 at 0x800EDCDC, Tomba!2 at 0x80089860; `external/mmx4`'s `symbols.us.txt` independently names 0x800EDCDC `InitHeap`). `crt0_setup` never sets `c->r[5]`, so the size argument is whatever the register file happened to hold.

**The HLE does NOT ignore a1 — that disjunct is false, and it was checked in the framework source rather than assumed.** `hle.cpp:355` is `case 0x39: heapInit(a0, a1); c->r[V0] = 0; return true;`, `a1` is read straight off `c->r[A1]` at `hle.cpp:331`, and `Hle::heapInit(addr, size)` (`hle.cpp:84`) copies it verbatim into `heap_size` and `blk[0].size`. That block size is the arena's whole capacity: `Hle::heapAlloc` (`hle.cpp:90`) skips any block with `blk[i].size < size` and returns 0 when nothing fits, so `a1` is exactly what decides whether every BIOS `A(33h)` malloc succeeds or returns NULL. Nor is the leftover value a controlled one: `Game` is `new`-allocated (`game.h:176`; `R3000::r[32]` has no initialiser, `dualcore.cpp:101`, `sbs.cpp:2094`) and nothing between construction and `native_boot.cpp:704 native_crt0` assigns `r[5]`, so the heap length is whatever that word happens to contain.

**What remains unmeasured is narrower and stated as such: whether Tomba!2's guest ever allocates through this arena at all.** If it never calls `A(33h)/A(37h)/A(38h)`, a wrong `heap_size` is inert and the port boots regardless — which is consistent with what is observed. That is a question about Tomba!2's code, not about the HLE, and it cannot be answered from this repo. **Item 4 stays a latent bug against the existing consumer, and the fix (`c->r[5] = heapsz`) is right either way; what is open is the blast radius, not the mechanism.**

Items 2 and 3 are the decisive ones. There is no value X4 can supply, because the correct answer is "this game has no such global". Pointing them at spare memory to keep the framework quiet would be a magic-value bandaid AND would inject two writes the real game never makes, diverging any RAM compare.

## The fix (generic, upstream, no X4 literal and no AGPL-derived line)

1. add `int32_t stackTopBias` to `GameConfig` — Tomba!2 = -8, X4 = 0 — and use it at line 221;
2. treat `heapSizePtr`/`heapBasePtr` == 0 as "this crt0 keeps them in registers only, do not store";
3. set `c->r[5] = heapsz` unconditionally before the dispatch — faithful to BOTH consumers, so this is a plain bug fix rather than a new knob.

Acceptance: `python3 tools/verify_crt0.py` must then print `verdict: COMPATIBLE — 10 of 10 checks match` for X4, and Tomba!2's own boot must be re-gated (its recorded group is unchanged by the fix; only the missing `r[5]` and the now-explicit bias move).

## Status / who does it

**NOT done, and not this repo's to do.** `external/psxport` here is a read-only pinned consumer; framework edits happen only in the workspace dev clone. Handed to the operator. Until then `game/core/game_config.cpp` keeps the boot group at zero with every measured value beside it as a `kCrt0*` constant, and RE-01 is `re-partial` — the RE is done, the plumbing is not.

### Note (2026-08-12)
OPERATOR MEASUREMENT ATTEMPT, 2026-08-12 — the obvious observation point does NOT work, recorded so the next attempt does not repeat it.

The framework-side fix was briefed to MEASURE the actual a1 first, because this card's own hedge ('either the HLE for A(39h) ignores a1 or the leftover value is benign') is falsifiable. Half of it is now settled from source: psxport runtime/recomp/hle.cpp:355 is `case 0x39: heapInit(a0, a1); c->r[V0] = 0; return true;` and Hle::heapInit (hle.cpp:84) assigns `heap_size = size` directly, while heapAlloc refuses any request larger than a block. **A(39h) does NOT ignore a1.** So the disjunction collapses to 'the leftover value is benign', which is unmeasured.

WHAT I TRIED AND WHY IT FAILED: instrumented A(39h) with an always-on `lucent::info("hle", "InitHeap(base=..., size=...)")` plus a novelty-capped heapAlloc-refusal warning, built Tomba2Engine against the framework worktree carrying it (build rc=0), and ran it headless under gpuguard with PSXPORT_GATE=1.

RESULT: **ZERO `[hle]` lines in the whole run.** The boot got as far as loading MAIN.EXE (entry 0x800896E0) and then aborted in Fmv::pace (rc=134, SIGABRT, 4s) — the boot-FMV path this repo's CLAUDE.md already records as skipped/deferred under GATE. But the absence of [hle] lines is NOT explained by that abort, because crt0 runs BEFORE the FMV.

THE LIKELY CAUSE, and the next attempt's actual target: crt0_setup reaches libcInit through `rec_dispatch(cfg->libcInit)`, and libcInit is the recompiled BIOS THUNK (`addiu t2,0xA0; jr t2; addiu t1,0x39`). So the call may never reach Hle::dispatchBios's A-table at all on this path — in which case instrumenting case 0x39 cannot observe it, and whatever sets up the heap is elsewhere. Observe at `crt0_setup` itself (log c->r[4] and c->r[5] immediately before the rec_dispatch) rather than at the BIOS table, and separately determine whether A(39h) is reached on ANY leg.

SECONDARY: use a leg that does not abort in the FMV — PSXPORT_ORACLE=1, or GATE+RENDER_PSX per the documented combination — so the run survives long enough to be evidence about anything downstream of boot.
