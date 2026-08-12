---
id: I004
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/code_scan.py — does a disc file contain R3000A code, or only data? (the overlay census)

## Validated by

Validated in BOTH directions on real data 2026-08-12 by --selftest: POSITIVE = the 64 KiB at the PS-EXE header's own declared entry pc0, which must read >=95% code-plausible and reads 99.4% of 16,367 windows; NEGATIVE = a media file chunk, which must read <=2% and reads 0.9%. --census refuses (exit 2) on a glob matching zero files, saying it scanned NOTHING and that this is not a 'no code found' result; the tool refuses (exit 2) when the framework's exe_similarity.py is not reachable through $PSXPORT_DIR, naming what it did not scan. HOW THE THRESHOLD WAS SET, because this is the part that could have gone wrong: the first POSITIVE gated the WHOLE .text at >=80% and FAILED at 79.6%. The threshold was NOT lowered. The cause is real — this game's t_size covers its rodata and a 161-entry path table (d_addr/d_size are 0), so whole-.text is a code/DATA mixture and gating on it would have forced a meaningless tuned-down number — so the positive was moved to a region the header itself certifies as code. Both numbers are reported. The discriminator itself is IMPORTED from external/psxport/tools/exe_similarity.py rather than reimplemented, so there is ONE calibrated copy (recalibrated + selftested 2026-08-12 over 5215 hand-disassembled code windows). BLIND SPOTS printed on every run: compressed/packed code reads as data and is indistinguishable from a texture; fragments under 64 bytes are invisible; it reads files as flat blobs and does not parse the .ARC container, so a small code member inside a large archive contributes a small percentage rather than standing out; and it says nothing about WHERE code would be loaded.

## Known failure modes

(none recorded yet)
