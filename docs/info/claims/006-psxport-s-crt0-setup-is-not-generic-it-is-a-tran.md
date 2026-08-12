---
id: C006
kind: claim
status: falsified
created: 2026-08-12
tags: framework,boot,residence-defect
depends: external/psxport/runtime/recomp/native_boot.cpp#crt0_setup, external/psxport/runtime/recomp/hle.cpp#heapInit, tools/verify_crt0.py
reconfirmed: 2026-08-12 16:11:09
verified_at: 2026-08-12 16:11:09
falsified_on: 2026-08-12
---

## Claim

psxport's crt0_setup is NOT generic — it is a transcription of Tomba!2's crt0, and it cannot run Mega Man X4's on four counts, two of which have no correct GameConfig value

## Evidence

Measured by running the SAME extractor over BOTH executables (tools/verify_crt0.py, which prints a per-step MATCHES/CONTRADICTS verdict against native_boot.cpp:218-232 and so cannot report a silent pass). 6 of 10 steps match X4: bss-clear semantics, stack top from a memory word, the 0x1FFFFFFF heap mask, the heap-size arithmetic, gp/sp/fp, and a0 = maskedHeapBase|0x80000000+4. The 4 contradictions: (1) line 221 hardcodes '- 8'; Tomba!2's MAIN.EXE really has 'addi v0,v0,-8' at 0x80089710 and X4's crt0 has NO bias instruction, so sp would be 0x801FFFF8 instead of 0x80200000; (2) line 226 stores heapsz to cfg->heapSizePtr unconditionally, but X4's crt0 stores it nowhere (1 absolute store in the whole function, and it is 'sw ra'), so field 0 writes to guest 0x00000000; (3) line 228 the same for heapBasePtr; (4) crt0_setup sets only c->r[4] before rec_dispatch(cfg->libcInit), yet BOTH games' libcInit is the BIOS A(39h) InitHeap thunk which takes the size in a1 (Tomba!2's crt0 computes a1=heapsz at 0x80089738 and X4's at 0x800DAEF8) — c->r[5] is never set, so this one is a latent bug against the EXISTING consumer too. Cross-check that makes (1) a measurement and not a reading of the C: the extractor re-derived all 12 boot-group values Tomba2Engine recorded independently by hand, including heapSizePtr 0x800ABEF8 and heapBasePtr 0x800ABEF4.

## What would falsify it

A framework change adding a stack-top bias field, making heapSizePtr/heapBasePtr==0 mean 'do not store', and setting c->r[5]=heapsz — after which verify_crt0.py's verdict for X4 must read COMPATIBLE (10 of 10). Also falsified if someone shows crt0_setup is not on X4's boot path at all: the claim assumes native_crt0 is unconditional, which was checked (native_boot.cpp:704, no GameHooks entry overrides crt0, and psx_fallback does not bypass it) but only by reading the framework source, not by running it.

## Re-confirmed 2026-08-12 16:11:09

Re-verified 2026-08-12 against the framework source at pin 324f7ccf. crt0_setup is unchanged since 409d7342 (git log -L over the function body), so all four contradictions still stand; deps are now SYMBOL-scoped, so a change to that function specifically is what marks this stale rather than any commit touching native_boot.cpp. CORRECTION to the evidence, and it matters: item 4's 'either the HLE for A(39h) ignores a1 or the leftover value is benign' was half FALSE. hle.cpp:355 is 'case 0x39: heapInit(a0, a1); c->r[V0] = 0; return true;', a1 is read off c->r[A1] at hle.cpp:331, and Hle::heapInit (hle.cpp:84) copies it verbatim into heap_size and blk[0].size — which Hle::heapAlloc (hle.cpp:90) treats as the arena's whole capacity ('blk[i].size < size' -> skip; nothing fits -> return 0). So a1 decides whether every BIOS malloc succeeds or returns NULL; the HLE does NOT ignore it. Nor is the leftover a controlled value: Game is new-allocated (game.h:176, dualcore.cpp:101, sbs.cpp:2094), R3000::r[32] has no initialiser, and nothing assigns r[5] between construction and native_boot.cpp:704 native_crt0. What is genuinely unmeasured is narrower and now stated that way in docs/issues/0005: whether Tomba!2's guest ever allocates through A(33h/37h/38h) at all — if it never does, a wrong heap_size is inert, which fits the observation that it boots. Same UNTRACKED-file baseline limitation as C005.

## FALSIFIED 2026-08-12

The DEFECT IT DESCRIBES IS FIXED, so the claim no longer holds of the current code — but it was TRUE when made and it is why the fix exists, which is worth more than the claim. psxport 726d10c9 moved the whole derivation into runtime/recomp/crt0_boot.h as a pure crt0_plan, and crt0_verify.h::crt0_audit now re-derives the group from the guest's own instruction stream at every boot and refuses a confirmed disagreement. All four non-generalising steps this claim named are addressed: the hardcoded -8 bias became a declared per-game field (MEASURED 0 for X4 and Toy Story 2, -8 for the other four, so 0 needed an explicit 'declared' flag rather than doubling as unset); the heap size/base stores became conditional, which stopped the framework writing both to GUEST ADDRESS 0 on every X4 boot; and a1 is now set, which had left every port calling InitHeap with a zero-capacity heap. Gated by tests/test_crt0_boot_group.cpp and tests/test_crt0_guest_audit.cpp. This repo pins that commit.

> Anything that cited this claim as proof must be re-checked. Grep the repo for it.
