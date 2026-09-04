---
id: C025
kind: claim
status: falsified
created: 2026-08-24
tags: RE-09,fastwait,pc_enh
depends: game/core/fast_wait.cpp#run_suppressed
falsified_on: 2026-08-24
---

## Claim

The loading-coroutine conversion is byte-exact: withholding only the per-field presentation commit inside the two retail CD wait bodies changes zero guest bytes, and the withheld fields must still tick emulated time and rotate the presenter ledger

## Evidence

2 MB guest RAM dumps at delivered fields 200 and 600 are BYTE-IDENTICAL with PSXPORT_X4_FASTWAIT 0 vs 1 (scratch/raw/fw-off-{200,600}.bin vs fw-on-*, cmp clean, 2026-08-24). Waits complete as one synchronous call after 50+6+155+23+4+362 condensed fields; boot reaches 0x8001DAF8 at 27 presented frames vs 83; ORACLE run shows zero fastwait lines at baseline frames 67/82/83. The intermediate design that skipped commit entirely overflowed the presenter capture (RQ_MAX 65536, scratch/logs/audio-after.log) — fixed by FramePresenter::commitUnpresented (framework worktree, 93/93 ctest)

## What would falsify it

any RAM-diff pair at equal delivered field that differs under FASTWAIT on/off, or a typed comparison run that logs an x4-fastwait line

## FALSIFIED 2026-08-24

The implementation it measured was discarded: fastwait now owns retail issuers 0x80013890/0x80013AD8, feeds the original guest callbacks synchronously from raw sectors, and performs no delivered-field presentation loop. Equal-field RAM dumps and commitUnpresented therefore do not verify the current loader.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
