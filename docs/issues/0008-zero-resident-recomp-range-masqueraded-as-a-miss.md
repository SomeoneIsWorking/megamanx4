---
id: 8
title: Zero resident recomp range masqueraded as a missing seed
status: resolved
symptom: runtime reports recomp-MISS for an address already present in generated rec_func_index
tags: recompiler,router,bootstrap,RE-02
created: 2026-08-21
updated: 2026-08-21
---

First native CRT0 boot reported [recomp-MISS] 0x800EDCDC. Adding it as a seed did not change the final 7,533-function set and the miss repeated; generated/shard_disp.c already contained both its rec_func_index and main_dispatch cases. Root cause: GameConfig shipped recMainLo=recMainHi=0, so overlay_router bypassed main_dispatch for every resident address. Wired the measured PS-X EXE physical range [0x00010000,0x0012F800), removed the unjustified seed, and extended verify_crt0.py with a positive range binding plus zero-range refusal. Software-Vulkan rerun executed InitHeap and dispatched guest main with no recomp miss before the separate CD/VSync hardware stall.
