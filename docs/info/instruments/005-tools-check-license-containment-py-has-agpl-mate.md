---
id: I005
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/check_license_containment.py — has AGPL material from mmx4 reached psxport?

## Validated by

RE-VALIDATED 2026-08-12 after two green-over-nothing defects were found by adversarial review and fixed
(see "Known failure modes" — read that FIRST; the 15/15 below was true and still missed both):
`--selftest` is now **19 checks, 0 failed**, the four new ones being the empty-checkout refusal, the
git-ignored-tree positive, the bare-clone class-B negative against a real psxport checkout, and the
no-baseline refusal. Validated in BOTH directions 2026-08-12 by --selftest: 15 checks, 0 failed, gating a clean framework tree (0 hits), a legitimate BIOS-HLE tree naming Sony kernel APIs plus the workspace doc that STATES this containment rule (0 HARD hits, but non-zero ADVISORY hits — silence there would mean the advisory tier is dead code), a planted leak (fires), and each hard class A/B/C reachable individually; plus both refusals (missing corpus exit 2, no framework checkout exit 2) and both subtraction assertions (a Sony declaration and a Sony #define macro must NOT become signatures, while a hand-named game symbol from the decomp's map must). PROVEN NON-VACUOUS rather than asserted: reintroducing the real '#'-stripping bug in a throwaway copy made the run report '15 checks, 2 failed' and exit 1 — an earlier version of that same check PASSED against the broken copy because the synthetic corpus never USED the macro, so the fixture now calls OpenEvent(SwCARD, EvSpIOE, EvMdNOINTR, NULL) exactly as the decomp does. REAL RUN against the framework dev clone: 314 text files scanned, 5,845 distinctive code identifiers and 144 phrases from 44 decomp source files, 0 HARD matches, 40 advisory across 8 files (all read and confirmed false positives). TWO FALSE-POSITIVE WAVES it produced first, with root causes, because either would have made the gate worthless: 637 hits that were all English words (cause: identifiers were mined from READMEs and from comment prose — fixed by mining class B only from code files with comments and string literals stripped), then 23 hits that were every doc explaining this very rule (cause: 'names the game' was treated as 'sources from the decomp' — fixed by splitting class A into a hard licence/source tier and an advisory name-mention tier). BLIND SPOTS printed on every run, and the first is the leak that actually worries us: paraphrased or re-typed logic, renamed identifiers, and struct layouts / field offsets / address maps carried in a human's head are invisible — for an enhancement port the likely contamination shape is someone internalising the player-object system and writing it into psxport from memory. Also invisible: anything under vendor/ (excluded by default, and --include-vendor's false-positive rate is unmeasured), binary and git-ignored files, and psxport's git HISTORY (working tree only). One further hole with a printed size: identifiers shared with a sibling game tree are subtracted as generic vocabulary (18 of 5,863), so a real leak of one of those 18 names would be invisible.

## Known failure modes

**2026-08-12 — IT REPORTED CLEAN OVER ZERO FILES, and the 15/15 selftest could not see it. FIXED, and
the fix is gated by two new checks.** Reproduced twice by an adversarial review, then re-reproduced
here. (a) The FRESH-CLONE DEFAULT: with `external/psxport` present as an uninitialised submodule
directory it printed `PASS — scanned 0 text files (0 listed via git ls-files -co --exclude-standard)`,
`0 hard matches`, **exit 0**. (b) A verbatim 1163-line AGPL decomp file
(`external/mmx4/src/main/1A5BC.c`) planted in a tree whose every file git ignores read the same way —
while the identical file in a plain directory gave `FAIL — 540 hit(s)`, exit 1. Two independent causes,
both in the ENUMERATOR rather than the detector: `scan_files()` did
`rels = out.stdout.split("\n") if ...`, and `''.split('\n')` is `['']` — TRUTHY — so a `git ls-files`
that SUCCEEDED with empty output took the git branch, enumerated nothing, and the filesystem-walk
fallback never ran; and `run()` refused for a missing corpus, zero signatures and no-checkout-found but
had no refusal for `total_scanned == 0`. Both are fixed (the split is filtered; `run()` dies with the
denominator: *scanned ZERO text files across N checkout(s) … NOTHING was compared*), and the selftest
now gates them: `refusal: an EMPTY framework checkout exits 2` and `positive: a leak in a tree whose
every file git IGNORES is still found`. Verified after the fix: case (a) → exit 2 with that message,
case (b) → `scanned 2 text files (2 listed via filesystem walk …)`, `FAIL — 540 hit(s)`, exit 1.
**The general lesson, worth more than the bug: `--selftest` was 15/15 because every fixture tree was
one the enumerator COULD see. A selftest that only ever feeds the instrument well-formed corpora
cannot catch an instrument that goes blind on a malformed one.**

**2026-08-12 — class B's "distinctive" was defined by directories OUTSIDE this repo, so a bare clone
FAILED with 27 false HARD hits. FIXED by shipping the exclusion set in-repo.** `default_baselines()`
subtracted the vocabulary of `../{Tomba2Engine,spyro,spider1,vagrant}/game`; a machine that clones
megamanx4 alone has none of them, the subtraction silently did not happen, and generic vocabulary
became signatures — measured in a bare-clone simulation: `NO BASELINE APPLIED` then
`FAIL — 27 hit(s) in the HARD classes`, all false (`checkpoint` ×24, an English word in
psxport/docs/oracle.md; `func_8003F698` ×3, an address-shaped recomp symbol in
psxport/docs/abi-extract.md). The exclusion set is now the tracked, human-readable
`docs/info/containment-baseline.txt` (25 names, regenerate with `--write-baseline`), sibling trees are
additive on top, and NO baseline at all is a REFUSAL (exit 2) instead of a wave of hard FAILs, because
a class-B result with nothing subtracted is not evidence. The selftest's real-corpus leg now runs the
BARE-CLONE configuration — tracked file only, no siblings, against a real psxport checkout, asserting 0
HARD hits — which is the case the old 15/15 never exercised (it called `default_baselines()`).
NEW BLIND SPOT this creates, stated because it is the price: **a real leak of one of the 25 excluded
names is invisible to class B**, and the file is only valid for the pinned corpus — a new mmx4 pin can
introduce new generic collisions, which show up as hard FAILs until someone regenerates and reads the
diff. Deliberately NOT excluded: psxport's own vocabulary (subtracting the scan target's words would
remove by construction whatever a leak looks like).

**2026-08-12 — an explicitly-set but wrong `$PSXPORT_DIR` was silently discarded. FIXED.**
`default_psxport_trees()` filtered candidates by `os.path.isdir`, so `PSXPORT_DIR=/nonexistent` exited
0 with a PASS having scanned `external/psxport` and `../psxport` instead of the checkout the operator
named. Now exit 2, matching `code_scan.py` / `discdump.py`.

**STILL TRUE, and not a bug: the blind-spot list on every run is the honest limit.** Paraphrased or
re-typed logic, renamed identifiers, and struct layouts / field offsets / address maps carried in a
human's head are invisible; so are `vendor/`, binary files, git-ignored files inside a tree that DOES
list files, and psxport's git HISTORY.
