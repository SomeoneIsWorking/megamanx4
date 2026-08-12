---
id: I002
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

tools/extract_exe.py — extract SLUS_005.61 from your own disc and identity-check it

## Validated by

POSITIVE path verified 2026-08-12: extracted 1,179,648 B via psxport's own discdump, sha1 213733031136d095ca275d6957695aa25011cfa5, PS-EXE header parsed and printed (pc0=0x800DAE8C, text 0x80010000+0x11F800, sp=0x801FFFF0, d_size=b_size=0), and the hash MATCHED the value read AT RUN TIME out of external/mmx4/check.us.txt — never a hardcoded copy, because a hardcoded copy would silently stop tracking the reference it claims to check. NOT YET EXERCISED, and therefore unproven: the MISMATCH path (needs a different-region dump) and the CANNOT-CHECK path (needs the mmx4 submodule absent). Both are coded to say explicitly what they did not verify rather than to pass quietly — the CANNOT-CHECK branch names the known-good expectation and refuses to substitute it silently — but neither branch has been run. Treat those two as unproven.

## Known failure modes

(none recorded yet)
