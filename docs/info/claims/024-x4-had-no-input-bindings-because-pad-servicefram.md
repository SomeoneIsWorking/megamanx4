---
id: C024
kind: claim
status: holds
created: 2026-08-24
tags: input,pad,RE-06,RE-07
depends: game/core/vsync_sync.cpp#deliver_field
---

## Claim

X4 had no input bindings because Pad::serviceFrame (the framework's only host-input-to-packet writer) was reachable only from Tomba!2's PC-driven native frame loop, which the guest-owned X4 path never runs; the field seam now services the pad once per delivered field. Slot-1 presence is explicit framework policy and stays false in shipping X4 until the host owns a distinct player-2 mask.

## Evidence

grep: zero serviceFrame call sites outside native_boot's Tomba2 loop before the change. AFTER: forced START -> router func_80012328 stores held/prev/edge 0x0800 (PADstart=1<<11, PSY-Q convention, LIBETC.H) at P1 0x80166C08/C0A/C0C (scratch/logs/input-probe1.log, 69,241 wwatch lines); a diagnostic slot-1 opt-in made the P2 trio decode correctly, proving the measured guest seam without making mirrored P1 input a shipping policy. Router decompile scratch/decomp/x4_router.c proves both slots decode from the two measured InitPAD buffers. Framework test_pad_slot1_policy proves the absent default and explicit opt-in.

## What would falsify it

a run where PSXPORT_FORCE_BUTTONS changes no byte in 0x80166C08..C0E or 0x80166D50..D56 while the router is traced reached, or a port whose guest reads slot 1 while slot1Connected defaults true somewhere it should not
