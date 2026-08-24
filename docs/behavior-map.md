# Behavior-difference map — every INTENTIONAL divergence from recomp_path (managed by tools/behavior.py)

Durable ledger of SANCTIONED deviations from the byte-exact reference. Primary axis = GUEST-MEMORY AFFECT (how much canon guest state a deviation touches). One `## ` block per
deviation, grouped by affect. `tools/behavior.py` = view · `... <words>` = search · `... check` = gate (a canon-affecting change must be SBS-suppressed).

**By affect:** 3 full
**By status:** 2 implemented · 1 planned

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
- **status:** implemented
- **flag:** PSXPORT_X4_FASTWAIT (read via x4::enh(x4::cv_fastwait) — never .get() at a call site)
- **original:** direct request issuer 0x80013890 and archive request issuer 0x80013AD8 start asynchronous ReadN transfers; ready callbacks 0x80013A20/0x80013E68 consume one sector at a time, and wait bodies 0x80014C70/0x80014A90 yield between polls while the loading-presentation task 0x80013530 draws
- **altered:** each measured issuer owns the complete load as one native call: its untouched generated setup runs once, title-owned code reads the request table's LBA/byte count, feeds consecutive raw sectors to the untouched generated callback with the retail FIFO cursor at raw+12, drains archive postprocess 0x80014780 after each callback, and requires terminal state 2 before returning. The retail wait predicates are therefore already terminal and execute zero yield/draw iterations; 0x80013530 is omitted.
- **guard:** force-suppressed under PSXPORT_ORACLE / PSXPORT_SBS / PSXPORT_SBS_MODE in game/core/enhancements.cpp x4::enh() — the single chokepoint every read passes through
- **owner:** game/core/fast_wait.{h,cpp} (per-Core synchronous load owner + scoped libcd leaves), game/core/recomp_register.cpp (reversible issuer/leaf registration)
- **notes:** USER directive 2026-08-24: "remove all loading screens, loading coro must be converted to single sync call". Archive handlers 0x800142BC/0x80014514 reject seven outstanding records; retail main calls consumer 0x80014780 once per loop, so the synchronous owner pumps it after every ready callback and requires processed/enqueued counters to match within the measured 16-slot ring. PsyQ LoadImage reaches set_alarm/get_alarm, whose measured VSync(-1) is a pure counter query; the scoped owner super-calls only that retail query and keeps every unmeasured mode fail-closed. Focused Clang build/lint and production-leaf tests pass. An uninstrumented real-disc run completed requests 64, 65, 113, and 51 (49/6/154/3 sectors) and remained live until timeout; exact destination-byte comparison and a presented-frame capture remain open. C025's equal-delivered-field RAM dumps and the commitUnpresented experiment measured a discarded presentation-withholding implementation and are explicitly not evidence for this one. This enhancement deliberately changes guest timing/state and makes no byte-exact claim.

## widescreen
- **class:** pc_enh
- **affect:** full
- **status:** implemented
- **flag:** PSXPORT_X4_WIDESCREEN (read via x4::enh(x4::cv_widescreen) — never .get() at a call site)
- **original:** the guest sets up a 4:3 projection; recomp_path renders exactly what the retail game renders
- **altered:** the guest GTE projection and draw environment widen to 16:9 so more world is visible without stretching
- **guard:** force-suppressed under PSXPORT_ORACLE / PSXPORT_SBS / PSXPORT_SBS_MODE in game/core/enhancements.cpp x4::enh() — the single chokepoint every read passes through
- **owner:** game/core/widescreen_controller.cpp
- **notes:** RE-08 retail census proves one global OFX/OFY/H setup at 160/120/512. The typed title consumer now latches 16:9 as OFX/width 214/428, changes only OFX and RECT.w around untouched retail bodies, and preserves exact 4:3/Oracle/SBS controls. Clang/unit/dependency gates pass against unlanded framework candidates; real pixel verification remains open until combined framework landing/pin and deterministic off/on PRESENT captures verify margins, central scale, culling, and 2D layout.
