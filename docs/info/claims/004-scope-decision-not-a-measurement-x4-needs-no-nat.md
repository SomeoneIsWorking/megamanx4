---
id: C004
kind: claim
status: holds
created: 2026-08-12
tags: scope,enhancements
depends: docs/plans/enhancements.md, game/core/enhancements.cpp
---

## Claim

SCOPE DECISION (not a measurement): X4 needs no native producers, no frame interpolation and no native depth, and its three deliverables are all pc_enh with affect: full

## Evidence

PROVENANCE: USER decision, 2026-08-12, quoted verbatim — 'Mega Man doesn't need native producers or lerp or native depth, it's already 60fps. It just needs widescreen patches (still hard work) and loading removals (again hard work). And I want to add co-op to it, drop-in, if I'm playing with X for example then second player can spawn as Zero.' The supporting fact offered is that the game already runs at 60fps, which is the USER's statement and has NOT been measured in this repo. THIS IS A DECISION RECORDED AS A CLAIM so a later session cannot 'discover' that the frame loop, the producers and native depth are missing and start building them: docs/codemap.md marks those four rows as skip-by-design (not-applicable) with this citation, and docs/re-frontier.md RE-05 is skip-by-design for the same reason. A claim whose evidence is a decision must SAY so — dressing a decision as a measurement is the failure mode this ledger exists to prevent.

## What would falsify it

the USER changing the scope decision, or a measurement in THIS repo showing X4 does NOT run at 60fps in the modes we care about (which has never been measured here — nobody has run the game)
