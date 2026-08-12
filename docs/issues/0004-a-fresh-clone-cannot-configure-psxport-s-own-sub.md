---
id: 4
title: a fresh clone cannot configure: psxport's OWN submodules are not reached by any documented step
status: resolved
symptom: cmake dies with add_subdirectory ... vendor/beetle-psx/deps/libchdr is not an existing directory, or vendor/lucent does not contain a CMakeLists.txt
tags: build,submodules,bootstrap
created: 2026-08-12
updated: 2026-08-12
---

The README's setup sequence produced a tree that cannot configure, and the tree AS DELIVERED was in
exactly that state (`git -C external/psxport submodule status` → `-904cc7d7 vendor/beetle-psx`,
`-07c58367 vendor/lucent`, both uninitialised).

## What fails, measured
* `cmake -S . -B build` with the DEFAULT `PSXPORT_DIR`: `add_subdirectory` on a non-existent
  `external/psxport/vendor/beetle-psx/deps/libchdr` (CMakeLists.txt:62) **and**
  `external/psxport/vendor/lucent does not contain a CMakeLists.txt file` (psxport.cmake:222).
* `tools/verify_decomp_targets.py` and `discdump.py` both die building `discdump` inside the
  submodule: `[discdump] FAILED: cmake -S .../external/psxport -B .../external/psxport/build`, exit 2.
  Both work with `PSXPORT_DIR=$PSX/psxport`, i.e. the tools were fine and the documented setup was not.
* `git clone --recurse-submodules` does NOT fix it: it ABORTS with `fatal: No url found for submodule
  path 'vendor/beetle-psx/deps/lightning/gnulib'` and leaves `vendor/lucent` EMPTY.
* `external/psxport/scripts/sync-submodules.sh` does not fix it either: it printed *"checked 2 of 2
  submodule(s), all at this repo's recorded gitlinks"* while `ls vendor/lucent` was still empty — the
  workspace's KNOWN-DEFECT-sync-submodules.md, i.e. the script certifies pins it never reached. And it
  is only invoked from `run.sh`, which agents must never run.
* The CMakeLists guard tested only `${PSXPORT_DIR}/cmake/psxport.cmake`, which EXISTS in this state, so
  the actionable message never printed.

## What works — the per-path, NON-recursive form
    git submodule update --init external/psxport external/mmx4
    git -C external/psxport submodule update --init vendor/lucent vendor/beetle-psx
Naming the paths sidesteps the url-less `deps/lightning/gnulib` that aborts `--recursive`. Verified:
default-`PSXPORT_DIR` configure + `--target megamanx4_seam` then build clean.

## Fixes landed
README "Getting started" and CLAUDE.md's build gate both carry the two-line form and state explicitly
that `--recurse-submodules` and `sync-submodules.sh` do NOT suffice, citing the KNOWN-DEFECT doc.
`CMakeLists.txt` now checks `vendor/lucent/CMakeLists.txt` and
`vendor/beetle-psx/deps/libchdr/CMakeLists.txt` and FATAL_ERRORs with that exact command (verified by
pointing PSXPORT_DIR at a stub checkout: the message fires instead of a raw add_subdirectory error).
`tools/discdump.py` names `PSXPORT_DIR` and the same per-path command in its build-failure message.

## Side effect fixed in the same pass
`discdump.py` built into `<PSXPORT_DIR>/build`, so a mere `discdump.py list` wrote a cmake build tree
INTO the read-only pinned submodule. It now prefers an existing binary and otherwise builds into this
repo's gitignored `scratch/build/discdump-<hash of the checkout>/` — keyed by checkout, so pointing
PSXPORT_DIR at a dev clone cannot silently reuse the submodule's binary. Verified: a full
`verify_decomp_targets.py` run reports MATCH and `external/psxport/build` does not exist afterwards.
