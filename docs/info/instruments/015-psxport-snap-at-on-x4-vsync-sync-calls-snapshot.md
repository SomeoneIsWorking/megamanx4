---
id: I015
kind: instrument
status: trusted
created: 2026-08-24
---

## Instrument

PSXPORT_SNAP_AT on X4 (vsync_sync calls snapshot_tick per delivered field)

## Validated by

positive: snap_150.bin's vblank counter 0x8011DC50 reads 0x96 = the requested field, proving field alignment (scratch/logs/snap-probe.log); negative: the pre-change binary wrote NO snap files because nothing called snapshot_tick (zero callers by grep). The FASTWAIT byte-exactness A/B (C025) rests on this instrument

## Known failure modes

(none recorded yet)
