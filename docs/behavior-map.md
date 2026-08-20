# Behavior-difference map — every INTENTIONAL divergence from recomp_path (managed by tools/behavior.py)

Durable ledger of SANCTIONED deviations from the byte-exact reference. Primary axis = GUEST-MEMORY AFFECT (how much canon guest state a deviation touches). One `## ` block per
deviation, grouped by affect. `tools/behavior.py` = view · `... <words>` = search · `... check` = gate (a canon-affecting change must be SBS-suppressed).

**By affect:** 3 full
**By status:** 3 planned

---

### **affect: full** — DELIBERATELY changes canon guest state. MUST be force-suppressed under PSXPORT_ORACLE / SBS (`guard` required) so byte-compares stay clean by construction.

## coop
- **class:** pc_enh
- **affect:** full
- **status:** planned
- **flag:** PSXPORT_X4_COOP (read via x4::enh(x4::cv_coop) — never .get() at a call site)
- **original:** single player only: one player struct, one camera target, pad slot 0 routed to it
- **altered:** a second player joins mid-play and controls the other hunter (P2 spawns as Zero when P1 is X)
- **guard:** force-suppressed under PSXPORT_ORACLE / PSXPORT_SBS / PSXPORT_SBS_MODE in game/core/enhancements.cpp x4::enh() — the single chokepoint every read passes through
- **owner:** game/core/enhancements.cpp
- **notes:** THE MOST INVASIVE pc_enh IN THE WORKSPACE. RE target is the PLAYER-OBJECT SYSTEM (RE-07), not the renderer, and the layout is UNKNOWN — docs/plans/enhancements.md stops there deliberately. RE-06 has measured and bound both InitPAD buffers, so the host input destination exists; the game-side route and player-object half are supported by nothing. THE SBS ORACLE IS ONLY MEANINGFUL WITH THIS OFF: a clean compare with co-op ON means the suppression fired, not that co-op is correct. Its own evidence gate is an OPEN QUESTION and has deliberately not been invented.

## fastwait
- **class:** pc_enh
- **affect:** full
- **status:** planned
- **flag:** PSXPORT_X4_FASTWAIT (read via x4::enh(x4::cv_fastwait) — never .get() at a call site)
- **original:** the game runs its own scripted wait states, fade ramps and frame-count timers to full length
- **altered:** those guest timers are collapsed, so transitions complete sooner
- **guard:** force-suppressed under PSXPORT_ORACLE / PSXPORT_SBS / PSXPORT_SBS_MODE in game/core/enhancements.cpp x4::enh() — the single chokepoint every read passes through
- **owner:** game/core/enhancements.cpp
- **notes:** This is loading-removal JOB B ONLY. Job A (raw I/O latency) is already largely gone BY CONSTRUCTION — psxport converts CD/file I/O to PC-native SYNCHRONOUS under the FAIL-FAST rule — and needs measuring, not building. Never quote one load-time number for both. Blocked on RE-09 (and RE-04 in practice: you cannot say what is a wait state until you know where the loads are). Which waits are SAFE to collapse is itself open.

## widescreen
- **class:** pc_enh
- **affect:** full
- **status:** planned
- **flag:** PSXPORT_X4_WIDESCREEN (read via x4::enh(x4::cv_widescreen) — never .get() at a call site)
- **original:** the guest sets up a 4:3 projection; recomp_path renders exactly what the retail game renders
- **altered:** the GUEST projection/FOV setup is widened (more world visible, not a stretched present), driven from game state
- **guard:** force-suppressed under PSXPORT_ORACLE / PSXPORT_SBS / PSXPORT_SBS_MODE in game/core/enhancements.cpp x4::enh() — the single chokepoint every read passes through
- **owner:** game/core/enhancements.cpp
- **notes:** affect=full, NOT none: psxport own widescreen is a host-side read-only overlay driven by a NATIVE renderer, but X4 has no native renderer, so a widescreen change here reaches the guest own projection setup. RE-08 has located the boot-time source lead (`func_8001213C`: GTE OFX/OFY/H = 160/120/512), but a later-write census and runtime verification are still required before enabling this planned behavior. See docs/plans/enhancements.md.
