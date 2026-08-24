---
id: C030
kind: claim
status: holds
created: 2026-08-25
tags: rendering,gte,framebuffer
depends: psxport.pin, game/core/x4_runtime.cpp#X4Runtime::guestVramIsPicture
---

## Claim

Stable Gte composite ownership must preserve both of X4s alternating framebuffer pages after the cold ownership build

## Evidence

Real X4 frame 180 changed from 0/691200 to 29921/691200 non-black and visibly renders the Mega Man X logo after psxport 75456947; the same pre-fix stream rendered 53631 non-black through the software PSX path and offline texture decode found nonblack texels across 37 sprites. Clean X4 build and 11/11 CTests pass at the fixed framework SHA.

## What would falsify it

if an exact same-build Gte capture again clears the displayed front page while its queued geometry targets only the alternating back-page band
