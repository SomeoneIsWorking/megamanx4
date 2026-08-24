---
id: 22
title: Gte erased X4 front framebuffer while drawing the back page
status: resolved
symptom: The real X4 Gte path emitted hundreds of valid textured sprites but frame 180 presented 0/691200 non-black pixels.
tags: rendering,gte,framebuffer,double-buffer,framework,RE-04
created: 2026-08-25
updated: 2026-08-25
---

## Root cause

X4 alternates the two PSX framebuffer pages. The Gte host path rasterized each ordering table into the correct back-page band but cleared the entire 1024x512 PC composite first, erasing the completed front page immediately before the display sampled it.

## Resolution

psxport `75456947` preserves the already-initialized composite under stable Gte ownership, while retaining the cold initialization clear, Native per-frame clearing, and independent Psx/guest-VRAM ownership.

## Evidence

Before: frame 180 was 0/691200 non-black. The same guest stream through the software PSX path was 53631/691200 non-black; offline decoding found valid white texels in 37 sprites. After: the Gte capture is 29921/691200 non-black (4.3288%) and visibly renders the Mega Man X logo. The framework policy test passes 3/3 cases and 5 checks. The X4 player and 11/11 Clang CTests pass against exact clean framework commit 75456947.
