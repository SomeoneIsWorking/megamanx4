---
id: C004
kind: claim
status: holds
created: 2026-08-12
tags: scope,enhancements
depends: docs/plans/enhancements.md
reconfirmed: 2026-08-24 23:09:41
verified_at: 2026-08-24 23:09:41
---

## Claim

SCOPE DECISION (not a measurement): X4 needs no native producers, no frame interpolation and no native depth, and its three deliverables are all pc_enh with affect: full

## Evidence

PROVENANCE: USER decision, 2026-08-12, quoted verbatim — 'Mega Man doesn't need native producers or lerp or native depth, it's already 60fps. It just needs widescreen patches (still hard work) and loading removals (again hard work). And I want to add co-op to it, drop-in, if I'm playing with X for example then second player can spawn as Zero.' The supporting fact offered is that the game already runs at 60fps, which is the USER's statement and has NOT been measured in this repo. THIS IS A DECISION RECORDED AS A CLAIM so a later session cannot 'discover' that the frame loop, the producers and native depth are missing and start building them: docs/project-goals.md records them as explicit non-goals, docs/project-state.md omits them from the missing-capability inventory, and docs/re-frontier.md RE-05 is skip-by-design for the same reason. A claim whose evidence is a decision must SAY so — dressing a decision as a measurement is the failure mode this ledger exists to prevent.

## What would falsify it

the USER changing the scope decision, or a complete cadence measurement in THIS repo showing X4 does NOT run at 60fps in the modes we care about (bounded front-end diagnostics have run, but no full-game cadence study has established or contradicted that premise)

## Re-confirmed 2026-08-20 22:21:54

Re-read the unchanged USER 2026-08-12 verbatim scope decision in docs/plans/enhancements.md while updating only the measured RE-06 input note; it still rules out native producers, interpolation and native depth.

## Re-confirmed 2026-08-21 00:55:36

Re-read the unchanged USER 2026-08-12 scope decision after the RE-06 documentation update; it still excludes native producers, interpolation, and native depth.

## Re-confirmed 2026-08-22 15:30:12

USER clarification 2026-08-22 again identifies X4 (SLUS_005.61) as already 60fps and widescreen-only, explicitly excluding lerp and its prerequisites. X4Runtime now encodes this directly; the full Clang build and 6/6 CTest pass.

## Re-confirmed 2026-08-22 17:48:53

2026-08-22: behavior.py check and cpp_policy pass; widescreen-only scope remains explicit after X4Runtime/thread work.

## Architecture correction 2026-08-22

This claim records the required USER scope; it is not proof that the current framework dependency
boundary already satisfies it. The shipping VBlank route calls `Fps60::frame_commit` for non-temporal
capture, real presentation, ledger reset, capture rotation, and pacing. No interpolated pass runs, but
the operational-independence claim is falsified as C018. Issue #12 owns the neutral frame-service
extraction. The scope decision itself still holds.

## Re-confirmed 2026-08-22 18:06:01

2026-08-22 architecture audit: the USER no-lerp scope still holds, while C018 is explicitly falsified because the current VBlank frame fence is misplaced inside Fps60; issue #12 owns the neutral framework extraction.

## Re-confirmed 2026-08-22 18:55:26

2026-08-22 candidate integration audit: USER scope remains widescreen-only for already-60fps X4; cpp_policy and x4_runtime pass, while issue #12 still truthfully records the misplaced non-temporal Fps60 fence rather than claiming interpolation independence.

## Re-confirmed 2026-08-24 23:09:41

The user scope decision remains unchanged. docs/plans/enhancements.md and the current X4Runtime continue to exclude native producers, interpolation, and native depth while retaining widescreen, synchronous loading, and co-op as the enhancement targets. This is scope provenance, not a measured cadence claim.
