---
id: 3
title: the AGPL containment gate reported clean over ZERO files, and its 15/15 selftest could not see it
status: resolved
symptom: check_license_containment.py prints PASS — scanned 0 text files, 0 hard matches, exit 0
tags: tooling,instrument,licensing,green-over-nothing
created: 2026-08-12
updated: 2026-08-12
---

A FIFTH instance of the class in docs/issues/0002, found by adversarial review on the day the tree was
created — in the ONE gate that protects five other ports from copyleft, and while its own `--selftest`
reported 15 checks / 0 failed.

## The symptom, reproduced twice
1. **The fresh-clone DEFAULT.** With `external/psxport` present as an uninitialised submodule
   directory: `[containment] scanned 0 text files (0 listed via git ls-files -co --exclude-standard)`
   then `PASS ... 0 hard matches`, **exit 0**.
2. **A verbatim 1163-line AGPL decomp file** (`external/mmx4/src/main/1A5BC.c`) planted in a tree whose
   every file git ignores: same `PASS — scanned 0 text files`, exit 0. The identical file in a plain
   directory gave `FAIL — 540 hit(s)`, exit 1. The DETECTOR was never the weak part.

## Root cause — two independent halves, both in the ENUMERATOR
* `scan_files()` did `rels = out.stdout.split("\n") if out.returncode == 0 else []`, and
  `''.split('\n')` is `['']` — TRUTHY. So a `git ls-files` that SUCCEEDED with empty output took the
  git branch, enumerated nothing, and the filesystem-walk fallback never ran.
* `run()` refused for a missing corpus, for zero signatures and for no-checkout-found, but had NO
  refusal for `total_scanned == 0`.

## Why the selftest was 15/15 anyway — the transferable lesson
Every fixture tree it fed the tool was one the enumerator COULD see. **A selftest that only ever feeds
an instrument well-formed corpora cannot catch an instrument that goes blind on a malformed one.**
Worse, the author had MET the symptom: moving the fixtures into a gitignored directory took the
selftest from 15/15 to 9/15, and the response was to move the fixtures back out and write a comment
explaining that "a fixture inside a gitignored directory cannot test a git-aware scanner". That
comment was the bug's alibi. Fixing the fixture and leaving the lie is the failure mode to remember.

## Fix
`scan_files()` filters the empty strings so "git listed nothing" falls through to the walk (and the
`how` string now says WHY it walked); `run()` dies with its denominator — *scanned ZERO text files
across N checkout(s) ... NOTHING was compared. This is NOT a clean tree.* Two new selftest checks:
`refusal: an EMPTY framework checkout exits 2` and `positive: a leak in a tree whose every file git
IGNORES is still found`. After the fix: case 1 → exit 2 with that message; case 2 → `scanned 2 text
files (2 listed via filesystem walk ...)`, `FAIL — 540 hit(s)`, exit 1.

## A second defect in the same tool, same review, same day
Class B's "distinctive" was defined by subtracting the vocabulary of `../{Tomba2Engine,spyro,spider1,
vagrant}/game` — directories OUTSIDE this repo. A bare clone has none, so the subtraction silently did
not happen and generic words became signatures: `NO BASELINE APPLIED` then `FAIL — 27 hit(s)`, all
false (`checkpoint` x24, `func_8003F698` x3). Fixed by shipping the intersection as the tracked,
readable `docs/info/containment-baseline.txt` (25 names, `--write-baseline` regenerates); sibling
trees stay additive; NO baseline at all is now a refusal (exit 2) rather than a wave of hard FAILs.
The selftest's real-corpus leg now runs the BARE-CLONE configuration against a real psxport checkout.
REJECTED, and worth recording as a dead end: the reviewer's suggestion to build that baseline from
"the sibling trees PLUS psxport". Subtracting the SCAN TARGET's own vocabulary removes by construction
whatever a leak would look like — the same circularity the workspace rejected for
`exe_similarity.py --sdk-filter K`. psxport is deliberately not in the file.
