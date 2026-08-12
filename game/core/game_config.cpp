// game_config.cpp — the Mega Man X4 (SLUS_005.61, USA) GameConfig: the guest-address literals the
// PSX-generic framework reads through `c->cfg->field`.
//
// READ THIS BEFORE FILLING ANYTHING IN.
//
// **Every address in this file is ZERO, because none has been reverse-engineered in this repo.** That
// is the honest value and it is deliberate: psxport fails fast on a zero it needs, whereas a
// plausible-looking WRONG address does not fail cleanly — it breaks boot or diverges the byte-compare
// in a way that reads as a framework bug. Each group names the open step in docs/re-frontier.md.
//
// An AGPL-3.0 MATCHING decompilation of this exact executable exists (external/mmx4, docs/references.md;
// its declared byte-exact build target is SHA-1 213733031136d095ca275d6957695aa25011cfa5, which is the
// SHA-1 of the image this repo extracts). Its symbol addresses are therefore OUR addresses with no
// translation, which makes it an excellent way to LOCATE a value fast. It is NOT a substitute for
// measuring one: a value copied out of it is a REFERENCE until this repo has confirmed it against these
// bytes, and the standing rule in this workspace is that where a reference and a measurement disagree,
// the measurement wins. When you fill a field, paste the disassembly line that justifies it, as
// spider1/game/core/game_config.cpp does — that citation is what makes the value reviewable a year from
// now. (Reading mmx4 also puts you under the AGPL firewall: what you learn stays in THIS repo. CLAUDE.md.)
#include "game_iface.h"

// MEASURED, from the PS-EXE header of the extracted SLUS_005.61 (tools/extract_exe.py prints it) and
// from the disc's SYSTEM.CNF. Kept as named constants rather than dropped into the struct below,
// because the struct's boot group is consumed AS A GROUP by the framework's crt0_setup: a lone entry
// PC beside a zeroed BSS range would make it run a wrong crt0 instead of refusing.
//
//   sha1(SLUS_005.61) = 213733031136d095ca275d6957695aa25011cfa5   (1,179,648 bytes)
//   PS-X EXE  pc0 = 0x800DAE8C   text = 0x80010000 + 0x11F800   sp = 0x801FFFF0
//             d_addr/d_size and b_addr/b_size are all 0 in the header — this game clears its own BSS.
//             (mmx4's splat config states .bss at 0x8012F418 size 0x46B20; that is the REFERENCE's
//             claim, not this repo's measurement, and it is not written into anything.)
//   SYSTEM.CNF  BOOT = cdrom:\SLUS_005.61;1   TCB = 4   EVENT = 16   STACK = 801FFF00
//
// RE-01 is exactly the step that turns these into the boot group.
static constexpr uint32_t kPsExeEntry     = 0x800DAE8Cu;   // header pc0
static constexpr uint32_t kPsExeTextAddr  = 0x80010000u;   // header t_addr
static constexpr uint32_t kPsExeTextSize  = 0x0011F800u;   // header t_size
static_assert(kPsExeEntry >= kPsExeTextAddr &&
              kPsExeEntry < kPsExeTextAddr + kPsExeTextSize,
              "the PS-EXE entry must lie inside the loaded text — if this fires, the header was "
              "misread and every number in this file's comment block is suspect");

// DESIGNATED initialisers, deliberately. GameConfig is initialised POSITIONALLY by the older
// consumers in this workspace, and the framework appends fields to it — which means a positional list
// silently re-binds every value after an inserted field. Binding by name makes an upstream insert a
// no-op here and an upstream RENAME a compile error naming the field, which is the signal we want.
// C++20 requires designators in declaration order; keep them so when adding one.
static const GameConfig g_x4_cfg = {
    // --- crt0 / boot ------------------------------------------------------------- RE-01, NOT DONE --
    // Left zero. See the constants above for what IS measured.
    .bssZeroLo = 0, .bssZeroHi = 0,
    .stackTopBase = 0, .stackTopBase2 = 0,
    .heapBase = 0,
    .heapSizePtr = 0, .heapBasePtr = 0,
    .gp = 0,
    .libcInit = 0,
    .gameMain = 0, .crt0 = 0,

    // --- recompiled MAIN .text range (physical) ---------------------------------- RE-02, NOT DONE --
    // These come from the RECOMPILER's own generated/overlay_table.h (REC_MAIN_LO / REC_MAIN_HI) so
    // they can never drift from the substrate they describe. There is no substrate yet, so they are
    // zero and this file does not #include that header — including a generated header that does not
    // exist would make the tree un-configurable rather than honestly incomplete.
    .recMainLo = 0, .recMainHi = 0,

    // --- disc key ----------------------------------------------- this port's own env name, not RE --
    // Not an RE fact but a port fact, and it belongs here because the framework must not know it: the
    // resolver used to hardcode the FIRST consumer's variable, so a second port set its own key,
    // nothing read it, and every boot ran with NO MEDIA behind an ordinary-looking log.
    // tools/resolve_disc.py implements the same key on the host side, and .env.example documents it.
    .discEnvVar = "PSXPORT_X4_DISC",

    // --- boot intro movies ------------------------------------------- deliberately EMPTY, and why --
    // Not a gap. The framework's native .STR player only plays what a port ASKS it to play, and this
    // port asks for nothing: there is no native boot here, so any movie is the GUEST's to play on the
    // substrate. The disc does carry 11 .STR streams (CAPCOM20, OP_U, X1-X4_U, Z1-Z5_U); naming one
    // here without knowing which the boot plays would be a guess wearing a citation.
    .bootFmv = { nullptr, nullptr, nullptr, nullptr },

    // --- per-frame OT / packet pool -------------------------------- RE-05, ➖ SKIP-BY-DESIGN here --
    // NOT a todo. This group only has a reader if the port stands up the framework's NATIVE frame loop,
    // and this port never will: X4 already runs at 60fps, so there is no interpolation to serve and no
    // native producer to drive (USER decision 2026-08-12, quoted in CLAUDE.md). The guest's own loop
    // runs on the substrate and owns its OT. If that decision is ever reversed, RE-05 is where it
    // starts — but zero here is the correct value for the port as scoped, not an outstanding gap.
    .otRegionBase = 0, .otRegionStride = 0,
    .packetPoolBase = 0, .packetPoolStride = 0,
    .otBasePtr = 0,
    .dwellCounter = 0,
    .poolPtrCur = 0, .poolPtrLast = 0,
    .clearOtagR = 0, .putDrawEnv = 0, .drawSync = 0,
    .irqEventClasses = {0, 0, 0},
    .dualviewRenderOrch = 0, .dualviewSubmit = 0,

    // --- scheduler task layout ------------------------------- N/A until a native frame loop exists --
    // The framework's PcScheduler is not wired for this port, and per the scope decision above it is
    // not going to be: GameHooks' scheduler entries are fail-fast stubs, so these values would have no
    // reader even if they were known.
    .taskTableBase = 0, .taskSlotStride = 0, .taskCount = 0,
    .curTaskPtr = 0,
    .stageStart = 0, .stageDemo = 0, .stageGame = 0,

    // --- overlay router slots --------------------------------------- ➖ NO OVERLAYS ON THIS DISC ---
    // MEASURED, and it is the defining structural fact of this port: **X4 has no code overlays. The
    // boot executable IS the whole engine.** All 163 disc files were enumerated and all 138 .ARC files
    // read in full; three independent signals agree (0 of 138 ARCs contain even ONE `jr $ra` epilogue
    // across 25.2 MiB; the calibrated code-window filter reads median 2.5% on ARCs against 99.4% at the
    // header-declared entry region; ≤9.1% of j/jal targets land inside .text vs 85.0% in the boot exe),
    // and the decomp's splat config declares exactly one code segment and not one overlay. See
    // docs/codemap.md and docs/info/claims/. BLIND SPOT, stated because the method cannot see past it:
    // this asserts "no PLAIN R3000A code outside the boot exe", not "no code" — packed/compressed code
    // inside an .ARC would read as a texture.
    //
    // So zero here is not "un-RE'd", it is the answer. The standing never-guess-an-overlay-base warning
    // still applies to anyone tempted by a number in the reference: an overlay is keyed BY its load
    // address, so a wrong base emits a whole module of correctly-decoded instructions at wrong
    // addresses and every jal target, pointer test and router lookup is then silently wrong.
    .overlaySlots = { {0, nullptr}, {0, nullptr}, {0, nullptr} },

    // --- CD chokepoints ---------------------------------------------------------- RE-04, NOT DONE --
    // Load-bearing for BOTH enhancement job A (raw I/O latency, which psxport's synchronous FAIL-FAST
    // CD path largely removes by construction) and for knowing where the game's own wait states are
    // NOT. Nothing located.
    .cdInit = 0, .cdCommand = 0, .cdSync = 0, .cdReadPrim = 0, .cdFileLoad = 0, .cdAsyncRead = 0,
    .voicePlay = 0, .voiceStop = 0, .lastSectorTracker = 0,
    .cdInlineLoad = 0,
    .cdCmdStream = 0,
    .cdCallbackTable = {0, 0, 0, 0},
    .cdCallbackFn = {0, 0, 0, 0},
    .cdGetSector = 0,
    .cdReadyCbPtr = 0,
    .cdLastPosBuf = 0,
    .cdReadStock = 0, .cdReadSync = 0,
    .cdSearchFile = 0,
    .dmaCallbackTable = 0,

    // --- pad driver -------------------------------------------------------------- RE-06, NOT DONE --
    // X4-SPECIFIC NOTE, and it is the one piece of good news co-op has: `padSlot1Buf` is the
    // FRAMEWORK'S EXISTING SECOND-CONTROLLER PATH — runtime/recomp/pad_input.cpp:550 reads
    //     uint32_t bufs[2] = { c->cfg->padSlot0Buf, c->cfg->padSlot1Buf };
    // so drop-in co-op's INPUT half is already framework-supported the moment RE-06 lands. What is NOT
    // supported by anything is the PLAYER-OBJECT half (one player struct, one camera, one input route):
    // that is RE-07, and it is the step this whole port turns on. Do not read a working second pad as
    // co-op being close.
    .padSlot0Buf = 0, .padSlot1Buf = 0, .padDriverFn = 0,
    .padSlotPtrTable = 0,
    .padSlotPtrStride = 0,

    // --- platform HLE (the hardware-sync primitives) ----------------------------- RE-01, NOT DONE --
    // ZERO MEANS "not RE'd, install nothing". initBuiltins() then registers no handler and says so;
    // a run that needs one hangs in the guest's real spin loop, which is the honest signal that the RE
    // is outstanding. The windows are zero too, so register_() refuses everything — this game has not
    // stated its memory map yet, and a window guessed from another game's map is how a handler lands
    // on an unrelated function.
    .hle = {},

    // --- rendering policy ------------------------------------------------- 1 while the guest draws --
    // The renderer clears to black on the principle "show ONLY what a native producer submitted". That
    // is right for a port whose native renderer owns the frame and WRONG for one still running the
    // guest's drawing code, where an upload into the display area IS visible on real hardware: logo
    // screens, FMV stills and menus that are uploads with no primitives render black. This port owns no
    // drawing at all AND never will (no native renderer — see the scope decision), so the guest's
    // uploads must survive. 1 is this port's permanent value, not a bootstrap placeholder.
    .preserveVramBackdrop = 1,

    // --- memory card ------------------------------------------------------ this port's own key/path --
    .cardEnvVar = "PSXPORT_X4_CARD",
    .cardDefaultPath = "scratch/saves/megamanx4.mcr",

    // --- frame pacing ------------------------------------------- 1 field per pacing call, and why --
    // The framework REQUIRES this field ("a new game MUST set this field"): zero used to fall through
    // to reading the first consumer's engine byte out of the scratchpad, which in any other game is
    // ordinary working memory, so a second consumer slept on garbage. THE SEMANTICS ARE BY CALLING
    // CADENCE, NOT BY THE GAME'S DISPLAY RATE — this game running at 60fps does NOT license a
    // different value, and changing it without measuring the pacing call site would be exactly the
    // kind of plausible-wrong number this file exists to refuse. A port that still runs the guest's own
    // frame loop and paces once per FIELD sets 1, which is this port's shape.
    .paceQuota = 1,

    .windowTitle = "Mega Man X4 (psxport)",
};

const GameConfig* x4_game_config() { return &g_x4_cfg; }

// Installs BOTH halves of the seam, because a Core's ctor snapshots them together — installing a
// config without its hooks leaves a Core holding a half-seam.
void x4_install_game_config() {
  extern const GameHooks* x4_game_hooks();   // game/core/game_hooks.cpp
  psxport_install_game(&g_x4_cfg, x4_game_hooks());
}
