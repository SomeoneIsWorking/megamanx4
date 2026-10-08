# Behavior-difference map — every INTENTIONAL divergence from the retail game (managed by tools/behavior.py)

Durable ledger of SANCTIONED deviations from the byte-exact reference. Primary axis = GUEST-MEMORY AFFECT (how much canon guest state a deviation touches). One `## ` block per
deviation, grouped by affect. `tools/behavior.py` = view · `... <words>` = search · `... check` = gate (a canon-affecting change must be comparison-suppressed).

**By affect:** 3 full
**By status:** 2 implemented · 1 planned

---

### **affect: full** — DELIBERATELY changes canon guest state. MUST be force-suppressed by the typed comparison-run role (`guard` required) so byte-compares stay clean by construction.

## coop
- **class:** pc_enh
- **affect:** full
- **status:** planned
- **flag:** PSXPORT_X4_COOP (read via x4::enh(x4::cv_coop) — never .get() at a call site)
- **original:** single player only: one player struct, one camera target, pad slot 0 routed to it
- **altered:** a second player joins mid-play and controls the other hunter (P2 spawns as Zero when P1 is X)
- **guard:** force-suppressed by psx::config::enh() in typed comparison runs; game/title/enhancements.cpp x4::enh() is the single title chokepoint every read passes through
- **owner:** game/title/enhancements.cpp
- **notes:** THE MOST INVASIVE pc_enh IN THE WORKSPACE. Its target is the PLAYER-OBJECT SYSTEM, not the renderer, and much of the layout is UNKNOWN — `docs/re-player-object.md` stops there deliberately. Both InitPAD buffers are measured and bound, so the host input destination exists; the game-side route and player-object half are supported by nothing. A comparison is meaningful only with this off: a clean compare with co-op requested means the suppression fired, not that co-op is correct. Its own evidence gate is an OPEN QUESTION and has deliberately not been invented.

## fastwait
- **class:** pc_enh
- **affect:** full
- **status:** implemented
- **flag:** PSXPORT_X4_FASTWAIT (read via x4::enh(x4::cv_fastwait) — never .get() at a call site)
- **original:** direct request issuer 0x80013890 and archive request issuer 0x80013AD8 start asynchronous ReadN transfers; ready callbacks 0x80013A20/0x80013E68 consume one sector at a time, and wait bodies 0x80014C70/0x80014A90 yield between polls while the loading-presentation task 0x80013530 draws
- **altered:** each measured issuer owns the complete load as one native call: its original guest setup runs once through Lightrec, title-owned code reads the request table's LBA/byte count, feeds consecutive raw sectors to the original guest callback with the retail FIFO cursor at raw+12, drains archive postprocess 0x80014780 after each callback, and requires terminal state 2 before returning. The retail wait predicates are therefore already terminal and execute zero yield/draw iterations; 0x80013530 is omitted.
- **guard:** force-suppressed by psx::config::enh() in typed comparison runs; game/title/enhancements.cpp x4::enh() is the single title chokepoint every read passes through
- **owner:** game/media/fast_wait.{h,cpp} (per-Core synchronous load owner + scoped libcd leaves), game/execution/native_overrides.cpp (image-scoped issuer/leaf registration)
- **notes:** USER directive 2026-08-24: "remove all loading screens, loading coro must be converted to single sync call". Archive handlers 0x800142BC/0x80014514 reject seven outstanding records; retail main calls consumer 0x80014780 once per loop, so the synchronous owner pumps it after every ready callback and requires processed/enqueued counters to match within the measured 16-slot ring. The native frame-loop migration now traps every guest VSync mode, including the former setup/query exceptions inside this route. The loader's non-VSync mechanics remain focused-test-covered, but it is not currently a working product claim until those calls move to direct native timing owners and a new launch verifies the combined route. This enhancement deliberately changes guest timing/state and makes no byte-exact claim.

## widescreen
- **class:** pc_enh
- **affect:** full
- **status:** implemented
- **flag:** PSXPORT_X4_WIDESCREEN (read via x4::enh(x4::cv_widescreen) — never .get() at a call site)
- **original:** the guest sets up a 4:3 projection and renders the retail composition
- **altered:** the guest's visibility cull widens by the 16:9 margin and the record path's canvas shows what the guest draws there; the projection and draw environment stay retail
- **guard:** force-suppressed by psx::config::enh() in typed comparison runs; game/title/enhancements.cpp x4::enh() is the single title chokepoint every read passes through
- **owner:** game/widescreen/widescreen_controller.cpp
- **notes:** The retail image has one global OFX/OFY/H setup at 160/120/512. On the record path the framework plan keeps OFX 160 and RECT.w 320 (the canvas adds 54 columns each side at 16:9), so the title's projection owner changes nothing the guest draws with; only the seven cull sites widen. Guest 2D stays as drawn, centred. STR movies hold 4:3. Pixel verification is open: no 16-bit picture past boot is reachable (`docs/issues/0037`).
