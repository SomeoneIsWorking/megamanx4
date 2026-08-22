---
id: C012
kind: claim
status: holds
created: 2026-08-22
tags:
depends: tools/verify_projection.py#verify
---

## Claim

MMX4 has one global retail projection setup and no later CR24/CR25/CR26 writer in its resident executable.

## Evidence

tools/verify_projection.py --check scanned all 294,400 loaded words of retail SLUS_005.61 and found exactly six CR24/25/26 CTC2 writers, all in InitGeom/SetGeomOffset/SetGeomScreen; one call to each from func_8001213C; OFX=160, OFY=120, H=512. --selftest accepted retail and rejected changed OFX, removed call, and extra raw writer (4/4).

## What would falsify it

The retail executable identity changes, tools/verify_projection.py changes, or any runtime observation finds a projection write not represented by the resident image.
