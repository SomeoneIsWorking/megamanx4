---
id: C021
kind: claim
status: holds
created: 2026-08-22
tags: widescreen,rendering,architecture
depends: game/core/native_overrides.cpp#publishProjection
reconfirmed: 2026-08-24 23:09:52
verified_at: 2026-08-24 23:09:52
---

## Claim

SLUS_005.61's title-owned widescreen consumer changes only the measured OFX and draw-environment width, preserves exact 4:3 identity, and has no operational Fps60 dependency against the typed framework candidate

## Evidence

Retail tools/verify_projection.py proves the sole SetGeomOffset 0x800E90C8 and SetDefDrawEnv 0x800E9354 publications. The image-keyed native overrides call their authenticated original guest bodies through Lightrec; tests/test_x4_runtime.cpp drives the production WidescreenController with 4:3 and 16:9 plans and proves OFX/width 160/320 -> 214/428 while OFY/H/x/y/h/UV/color/order remain unchanged. The temporal-dependency policy check covers the shipping sources and its neutral positive plus interpolation mutations. Clang links the native/Lightrec product and the focused contracts pass.

## What would falsify it

Falsified if a real wrapper changes any guest field other than OFX/RECT.w, if the 4:3 path differs from 160/320, if the dependency gate accepts an Fps60 product/call/include, or if deterministic wide pixels show crop/stretch instead of newly visible margins.

## Re-confirmed 2026-08-22 19:25:53

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.

## Re-confirmed 2026-08-22 19:26:00

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.

## Re-confirmed 2026-08-22 19:26:07

Real-disc startup against the isolated typed framework candidate reaches the measured retail wrapper. scratch/logs/re08-typed-wide-boot.log logs 320x240 -> 428x240, OFX=214, draw width=428 with widescreen requested; scratch/logs/re08-typed-4x3-boot.log logs exact 320x240, OFX=160, draw width=320 with it disabled. Both bounded controls exit only through the external timeout after boot continues; no title-local stretch/native path is involved.

## Re-confirmed 2026-08-24 23:09:52

On commit a53c255, verify_projection.py scanned all 294,400 words, proved the six sole projection writers and one boot call each, and passed 4/4 controls. mmx4_runtime_test and the no-temporal gates passed inside full Clang CTest 11/11, proving 4:3 identity, 16:9 OFX/width 214/428, and no linked temporal product.
