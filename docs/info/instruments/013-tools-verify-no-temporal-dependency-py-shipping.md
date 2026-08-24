---
id: I013
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

tools/verify_no_temporal_dependency.py — shipping X4 operational interpolation dependency gate

## Validated by

Positive neutral presentation source passes; five independent mutations adding fps60.h, Fps60 construction, Game::fps60 call, FPS60 macro, and temporal hook call are each rejected. This is the source-closure half only; I016 owns shipping-binary symbols.

## Known failure modes

It cannot see link-time dependency closure. It previously passed while `megamanx4_port` contained the
complete Fps60 implementation (38 matching symbols). Never cite I013 alone as proof that the shipping
binary contains no interpolation dependency; use I016 as well.
