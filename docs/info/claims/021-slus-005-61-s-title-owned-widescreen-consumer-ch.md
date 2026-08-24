---
id: C021
kind: claim
status: holds
created: 2026-08-22
tags: widescreen,rendering,architecture
depends: game/core/recomp_register.cpp#publish_projection
reconfirmed: 2026-08-22 19:26:07
verified_at: 2026-08-22 19:26:07
---

## Claim

SLUS_005.61's title-owned widescreen consumer changes only the measured OFX and draw-environment width, preserves exact 4:3 identity, and has no operational Fps60 dependency against the typed framework candidate

## Evidence

Retail tools/verify_projection.py proves the sole SetGeomOffset 0x800E90C8 and SetDefDrawEnv 0x800E9354 publications. game/core/recomp_register.cpp wraps their untouched generated bodies; tests/test_x4_runtime.cpp drives the production WidescreenController with 4:3 and 16:9 plans and proves OFX/width 160/320 -> 214/428 while OFY/H/x/y/h/UV/color/order remain unchanged. tools/verify_no_temporal_dependency.py scans 18 shipping sources and its neutral positive plus five interpolation mutations pass. Clang links the full generated port and CTest passes 8/8 against the isolated typed framework worktree.

## What would falsify it

Falsified if a real wrapper changes any guest field other than OFX/RECT.w, if the 4:3 path differs from 160/320, if the dependency gate accepts an Fps60 product/call/include, or if deterministic wide pixels show crop/stretch instead of newly visible margins.

## Re-confirmed 2026-08-22 19:25:53

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.

## Re-confirmed 2026-08-22 19:26:00

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.

## Re-confirmed 2026-08-22 19:26:07

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.
