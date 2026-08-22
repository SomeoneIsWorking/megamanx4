---
id: I012
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

tools/verify_projection.py — complete retail OFX/OFY/H writer and call-site census

## Validated by

On retail SLUS_005.61, --check accepted the measured six-writer/three-call chain; --selftest then changed OFX, removed SetGeomOffset, and inserted an extra raw CR24 writer, and rejected all three (4/4 total cases).

## Known failure modes

(none recorded yet)
