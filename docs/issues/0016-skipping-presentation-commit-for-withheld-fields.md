---
id: 16
title: Discarded presentation-withholding fastwait accumulated the render-queue capture
status: resolved
symptom: the former wait-body override overflowed RQ_MAX while withholding presentation commits
tags: presentation,fastwait,framework,RE-09
created: 2026-08-24
updated: 2026-08-24
---

## Root cause
The discarded implementation still executed every retail load field but skipped `FramePresenter::commit`. That call also rotates/reset the capture (`resetCapture`, `beginLedgerFrame`, fence), so every supposedly suppressed field accumulated into one capture until RQ_MAX overflowed (`scratch/logs/audio-after.log`, about 33k fields).

## Disposition
`FramePresenter::commitUnpresented` made that experiment internally consistent and its hermetic test proved capture rotation without presentation. It is not the shipping fix and is not a fastwait dependency: the entire wait-body/presentation-withholding design was retired.

The current title-owned loader overrides retail request issuers 0x80013890/0x80013AD8, performs the table-bounded raw-sector/callback work synchronously, and returns at terminal state 2. The retail waits therefore deliver no condensed fields and create no capture-rotation problem. C025 retains the old byte-identical evidence with status `falsified` so it cannot be cited for the new implementation.
