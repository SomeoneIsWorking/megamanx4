---
id: I006
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/verify_crt0.py — re-derives the crt0 boot group from a PS-X EXE, DIFFS IT AGAINST THE SHIPPING FILE (game/core/game_config.cpp), and judges it against psxport's crt0_setup

## Validated by

Gated on BOTH classes, re-run 2026-08-12 after the shipped-vs-measured rebuild: `python3 tools/verify_crt0.py --selftest --cross ../Tomba2Engine/scratch/bin/tomba2/MAIN.EXE` -> **16/16 (4 positive, 12 negative), exit 0**; without --cross, 14/14 and it says loudly which case group did not run.

WHAT IT NOW COMPARES, which is the whole point: `--check` parses `game/core/game_config.cpp` and diffs its `kCrt0*`/`kPsExe*` constants against the values this run derived from the bytes — 17 comparisons (10 crt0 constants incl. the `kCrt0Entry = kPsExeEntry` alias resolved through the parser, 2 measured-ABSENT fields asserted to have NO constant, 3 PS-EXE header facts, the sha1 the file CITES for the image (hashed and diffed), and the `g_x4_cfg` crt0 group's all-zero-or-all-filled state). It keeps NO expectation table of its own.

POSITIVES: the shipped constants equal the measurement (17/17); the two shape facts with no GameConfig field (`stackTopBias=0`, `libcArgs=a0,a1`) hold; the framework verdict is INCOMPATIBLE with >=3 contradictions; and the STRONGEST one — run on Tomba!2's MAIN.EXE it reproduces all 12 boot-group values `Tomba2Engine/game/core/game_config.cpp` recorded independently by hand (12/12), which is what proves it reads binaries rather than echoing an expectation.

NEGATIVES it must and does fail on — **both sides of the comparison are sabotaged, in the shipping path itself (`check_shipped`, the same function `--check` calls)**: a flipped immediate in the bss-bound instruction moves the derived `bssZeroHi` (0x80175F38 -> 0x80175F78) and disagrees with the shipped constant; a hand-edited constant in a copy of the real `game_config.cpp` is caught for `kCrt0GameMain = 0x80999999u`, `kCrt0LibcInit = 0xDEADBEEFu`, the header fact `kPsExeTextAddr = 0x80020000u`, and a hand-edited cited sha1 (which would attribute the measurement to an image nobody read); a HALF-filled `g_x4_cfg` crt0 group is caught as PARTIALLY filled (the state that looks like progress); `main()` at 0x80012024 is REFUSED as "not a crt0 by shape" with the instruction count walked and the events seen; and three malformed-corpus shapes — a MISSING path, a **0-BYTE file** and a **GARBAGE file** — all refuse with exit 2 and the file's size, instead of the uncaught `ValueError` from `psexe.load` that the last two used to raise. A missing or constant-less shipping file also refuses (exit 2), never "nothing to compare, pass".

Shown FAILING on purpose, on the real tree: setting `kCrt0GameMain -> 0x80999999u` in `game/core/game_config.cpp` gives `CHECK FAILED: 1 disagreement(s) ... kCrt0GameMain ships 0x80999999 but this run measured gameMain = 0x80012024`, exit 1, and `--selftest` 13/14 exit 1. Deleting the malformed-corpus refusal from `load_exe` gives `--selftest` 12/14 exit 1 with the 0-BYTE and GARBAGE cases red.

Blind spots it states itself: immediate-only tracking; it does not follow the bss loop's backward branch; it walks straight-line code with delay slots applied before their branch; it reads the STATIC image so it says nothing about runtime values; and the C parser is regex-based over comment-stripped text, so a `game_config.cpp` rewritten in a shape it cannot read is a REFUSAL, not a pass.

## Known failure modes

**FIXED 2026-08-12 — it verified ITSELF and certified an ungated shipped value.** Until this date the tool held its own copy of the eleven measured addresses (`X4_EXPECT`) and asserted the BINARY matched that table; `game/core/game_config.cpp` held a second copy as `kCrt0*` constants; and nothing compared the two. Proven by sabotage, not argued: with `kCrt0GameMain = 0x80999999`, `kCrt0LibcInit = 0xDEADBEEF` and `kCrt0StackTopBase = 0x80001234` in the shipping file, `--check` printed "CHECK PASSED: all 13 recorded fields re-derived from these bytes" and `--selftest` printed 8/8, both exit 0. The `static_assert`s in that file did not help and could not: they check the constants' internal relations, and `hi - lo == 0x46B20` holds just as well when both values are wrong. Anything that cited I006 or C005 as evidence that the SHIPPED boot group was correct, before this date, was citing a gate that did not cover it. The table is now deleted and the shipping file is the only copy.

**Still true, and not a defect:** the tool says nothing about whether the values are right at RUNTIME, and RE-01 remains `re-partial` — the group cannot be written into `GameConfig` at all while psxport's `crt0_setup` bakes in Tomba!2's crt0 shape (issue #5, claim C006).
