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
//   SYSTEM.CNF  BOOT = cdrom:\SLUS_005.61;1   TCB = 4   EVENT = 16   STACK = 801FFF00
static constexpr uint32_t kPsExeEntry     = 0x800DAE8Cu;   // header pc0
static constexpr uint32_t kPsExeTextAddr  = 0x80010000u;   // header t_addr
static constexpr uint32_t kPsExeTextSize  = 0x0011F800u;   // header t_size
static_assert(kPsExeEntry >= kPsExeTextAddr &&
              kPsExeEntry < kPsExeTextAddr + kPsExeTextSize,
              "the PS-EXE entry must lie inside the loaded text — if this fires, the header was "
              "misread and every number in this file's comment block is suspect");

// ──────────────────────────────────────────────────────────────────────────────────────────────────
// RE-01: THE crt0 BOOT GROUP IS NOW MEASURED. IT IS STILL NOT IN THE STRUCT, AND THAT IS THE FINDING
// ──────────────────────────────────────────────────────────────────────────────────────────────────
// 2026-08-12. The entry function at pc0 was disassembled and symbolically executed from these bytes,
// straight through to its terminating `break` (43 instructions). Reproduce, with per-field citations
// and a both-classes selftest:
//
//     python3 tools/verify_crt0.py --check
//     python3 tools/verify_crt0.py --selftest [--cross <another game's PS-X EXE>]
//
// **`--check` READS THIS FILE.** It parses the `kCrt0*`/`kPsExe*` constants below and diffs them
// against what it measures from the bytes in the same run — 16 comparisons, one source of truth, so a
// hand-edit of EITHER side goes red. That is not how it started: the tool used to keep its own copy of
// the table and only assert the BINARY matched it, this file kept a second copy, nothing compared the
// two, and with `kCrt0GameMain` set to 0x80999999 and `kCrt0LibcInit` to 0xDEADBEEF both `--check` and
// `--selftest` still passed. The `static_assert`s below are worth keeping and were never this: they
// check the constants' RELATIONS, and `hi - lo == 0x46B20` holds just as well when both are wrong. So
// when you fill a field here, the tool is what proves the number; when you EDIT one, the tool is what
// catches you. `--check` also asserts the struct's crt0 group is either ALL ZERO (its state today, see
// below) or every field naming its measured constant — a partial fill is red.
//
// The values below are OURS — derived from this executable, not copied. They happen to CONFIRM the
// one hypothesis that was on the table (external/mmx4's splat config claimed .bss at 0x8012F418 size
// 0x46B20; the clear loop measures [0x8012F418, 0x80175F38), i.e. exactly 0x46B20). Confirmed, not
// pasted — the loop bounds come out of `lui/addiu` + `sltu` at 0x800DAE8C..0x800DAEA8.
//
//   0x800DAE8C  lui v0,0x8013 / addiu v0,v0,-3048     v0 = 0x8012F418   .bss low
//   0x800DAE94  lui v1,0x8017 / addiu v1,v1,24376     v1 = 0x80175F38   .bss high (exclusive)
//   0x800DAE9C  sw zero,0(v0) / addiu v0,v0,4 / sltu at,v0,v1 / bne     the clear loop, 0x46B20 bytes
//   0x800DAED0  lw v0,0(a0)   a0 = 0x800DAF38+4       mem[0x800DAF3C] = 0x00200000  stack-top word
//   0x800DAED8  or sp,v0,0x80000000                   sp = fp = 0x80200000  — AND THERE IS NO BIAS
//   0x800DAEE0  lui a0,0x8017 / addiu a0,a0,24376     heap base 0x80175F38 (== .bss high), then
//   0x800DAEE4  sll a0,3 / srl a0,3                   masked to 0x00175F38
//   0x800DAEF0  lw v1,-13452(v1)                      mem[0x8011CB74] = 0x00008000  stack reserve
//   0x800DAEF8  subu a1,v0,v1 / subu a1,a1,a0         heap size = 0x820C8 (532,680 bytes)
//   0x800DAF08  sw ra,-3048(at)                       saves its own ra at 0x8012F418 (== gp+0)
//   0x800DAF0C  lui gp,0x8013 / addiu gp,gp,-3048     gp = 0x8012F418
//   0x800DAF18  jal 0x800EDCDC  (delay: addi a0,a0,4) a0 = 0x80175F3C, a1 = 0x820C8
//                                                     0x800EDCDC is `addiu t2,0xA0; jr t2;
//                                                     addiu t1,0x39` = BIOS A(39h) InitHeap(ptr,size)
//   0x800DAF2C  jal 0x80012024                        game-main
//   0x800DAF34  break                                 crt0 never returns
//
// So the MEASURED group is:
//     bssZeroLo 0x8012F418   bssZeroHi 0x80175F38   stackTopBase 0x800DAF3C   stackTopBase2 0x8011CB74
//     heapBase  0x80175F38   gp        0x8012F418   libcInit     0x800EDCDC
//     gameMain  0x80012024   crt0      0x800DAE8C   heapSizePtr/heapBasePtr: THIS crt0 HAS NEITHER
//
// **WHY THE STRUCT BELOW IS STILL ZERO: the framework's crt0_setup cannot run this crt0, and no
// assignment of these fields makes it able to.** external/psxport/runtime/recomp/native_boot.cpp:218
// is a faithful transcription of TOMBA!2's crt0 wearing generic clothes. Six of its ten steps match
// X4 exactly (bss clear semantics, stack top from a memory word, the 0x1FFFFFFF heap mask, the heap-size
// arithmetic, gp/sp/fp, and a0 = maskedHeapBase|0x80000000 + 4). Four do not:
//
//   1. line 221 hardcodes `mem_r32(cfg->stackTopBase) - 8`. Tomba!2's crt0 really does `addi v0,v0,-8`
//      at 0x80089710; X4's has NO such instruction. sp would come out 0x801FFFF8, 8 bytes low.
//   2. line 226 `mem_w32(cfg->heapSizePtr, heapsz)` is unconditional. X4's crt0 stores the heap size
//      NOWHERE — it passes it in a1. Leaving the field 0 writes the heap size to guest 0x00000000.
//   3. line 228 `mem_w32(cfg->heapBasePtr, a0)` — same, a second write to guest 0x00000000.
//   4. crt0_setup sets only `c->r[4]` before `rec_dispatch(c, cfg->libcInit)`. Both games' libcInit is
//      the BIOS A(39h) InitHeap thunk and BOTH pass the size in a1, so `c->r[5]` is simply missing:
//      X4's heap would be initialised with whatever was left in the register file.
//
// Fields 2 and 3 are the decisive ones: there is no address this port could put there that is not a
// lie, because the correct answer is "this game does not have that global". Pointing them at scratch
// memory to keep the framework quiet would be exactly the magic-value bandaid this file exists to
// refuse — and it would inject two writes the real game never makes, diverging any RAM compare.
//
// THE PROPER FIX IS A FRAMEWORK CHANGE, and it is generic (no X4 literal, no AGPL-derived line, so it
// is safe to land in psxport): add `int32_t stackTopBias` to GameConfig (Tomba!2 = -8, X4 = 0); treat
// heapSizePtr/heapBasePtr == 0 as "this crt0 keeps them in registers only — do not store"; and set
// `c->r[5] = heapsz` unconditionally, which is faithful to BOTH consumers and is a plain bug fix
// rather than a new knob. Tracked in docs/re-frontier.md RE-01 and docs/issues/. Until it lands, zero
// is the honest value and the framework fails fast on it. THE RE IS DONE; THE PLUMBING IS NOT.
static constexpr uint32_t kCrt0BssZeroLo    = 0x8012F418u;
static constexpr uint32_t kCrt0BssZeroHi    = 0x80175F38u;
static constexpr uint32_t kCrt0StackTopBase = 0x800DAF3Cu;
static constexpr uint32_t kCrt0StackTopBas2 = 0x8011CB74u;
static constexpr uint32_t kCrt0HeapBase     = 0x80175F38u;
static constexpr uint32_t kCrt0Gp           = 0x8012F418u;
static constexpr uint32_t kCrt0LibcInit     = 0x800EDCDCu;   // BIOS A(39h) InitHeap thunk
static constexpr uint32_t kCrt0GameMain     = 0x80012024u;
static constexpr uint32_t kCrt0Entry        = kPsExeEntry;   // crt0 IS the PS-EXE entry
// THE STACK-TOP BIAS, and it is 0 BECAUSE THE INSTRUCTION IS NOT THERE — not because nobody looked.
// The stock PSY-Q crt0 does `addi v0,v0,-8` between loading the stack-top word and OR-ing it into $sp;
// four of this workspace's five executables really do (Tomba!2 @0x80089710, Spyro @0x8005B910,
// Spider-Man @0x800873CC, Vagrant Story @0x8001F574). X4's crt0 goes straight from
// `lw v0,0(a0)` @0x800DAED0 to `lui t0,0x8000 / or sp,v0,t0` @0x800DAED4/D8 — there is no adjustment,
// so sp = 0x80200000 exactly and the heap-size subtraction is 8 bytes larger than the framework used to
// compute. Zero here is a MEASURED value, which is why psxport's `stackBias` field carries a separate
// `declared` flag: for this one field zero cannot double as "unset".
static constexpr int32_t  kCrt0StackBias    = 0;
static_assert(kCrt0BssZeroHi - kCrt0BssZeroLo == 0x46B20u,
              "the measured .bss size must stay 0x46B20 — if this fires, the clear-loop bounds were "
              "re-derived to something else and tools/verify_crt0.py --check is the arbiter");
static_assert(kCrt0HeapBase == kCrt0BssZeroHi,
              "this crt0 starts the heap exactly at the end of .bss; a divergence means one of the "
              "two was mis-derived");
static_assert(kCrt0Gp == kCrt0BssZeroLo,
              "gp points at the base of .bss in this crt0 (and the ra it saves at gp+0 is bss[0])");
static_assert(kCrt0BssZeroHi > kPsExeTextAddr + kPsExeTextSize,
              ".bss must END above the loaded text image — a .bss entirely inside .text would mean "
              "the clear loop wipes code, i.e. the bounds were misread");
// CORROBORATION, and the one thing about these bounds that looks wrong until you check it: .bss STARTS
// 0x3E8 bytes BELOW the end of the loaded text image (0x8012F418 < 0x8012F800), because t_size is
// rounded up to the 0x800 CD-sector boundary. Those 1000 overlapping bytes in the file were read and
// are ALL ZERO, so the clear loop destroys nothing — it re-zeroes the padding and continues into real
// .bss. If they were ever nonzero, the bounds would be misread and this whole block is suspect.
//   python3 -c "d=open('scratch/bin/megamanx4/SLUS_005.61','rb').read(); \
//               print(sum(1 for b in d[0x8012F418-0x80010000+0x800:0x11F800+0x800] if b))"   # -> 0
static_assert(kCrt0BssZeroLo < kPsExeTextAddr + kPsExeTextSize,
              "if .bss no longer starts inside the sector-padded text tail, the note above about the "
              "1000 zero bytes of overlap is stale and must be re-measured");

// DESIGNATED initialisers, deliberately. GameConfig is initialised POSITIONALLY by the older
// consumers in this workspace, and the framework appends fields to it — which means a positional list
// silently re-binds every value after an inserted field. Binding by name makes an upstream insert a
// no-op here and an upstream RENAME a compile error naming the field, which is the signal we want.
// C++20 requires designators in declaration order; keep them so when adding one.
static const GameConfig g_x4_cfg = {
    // --- crt0 / boot ------------------------------------------------ RE-01: MEASURED and NOW WIRED --
    // Every field is the kCrt0* constant above, each with the disassembly line behind it, and TWO
    // independent things diff those constants against the bytes rather than trusting this file:
    //   * tools/verify_crt0.py --check / --selftest, which PARSES this file (so a partial fill — the one
    //     failure state that looks like progress — is caught too);
    //   * psxport's own crt0_audit (external/psxport/runtime/recomp/crt0_verify.h), which at EVERY boot
    //     re-derives the group from the guest instruction stream at `crt0` and REFUSES to boot on a
    //     disagreement. That is the gate that makes `stackBias` safe to state here: no python tool has
    //     to be re-run for the shipped value to be compared to the measurement.
    //
    // heapSizePtr/heapBasePtr are 0 = ABSENT, and that is now a value the framework can express: this
    // crt0's ONLY absolute store is `sw ra` to 0x8012F418, so there is no heap-size or heap-base global
    // to write. psxport used to store both unconditionally, i.e. to guest 0x00000000; it now performs
    // neither store and SAYS "0 of 2 declared" in the boot log. Putting a plausible address here to keep
    // the framework quiet would inject two writes the real game never makes — and crt0_audit would now
    // catch it, because the guest crt0 has no such store to point at.
    .bssZeroLo = kCrt0BssZeroLo, .bssZeroHi = kCrt0BssZeroHi,
    .stackTopBase = kCrt0StackTopBase, .stackTopBase2 = kCrt0StackTopBas2,
    .heapBase = kCrt0HeapBase,
    .heapSizePtr = 0, .heapBasePtr = 0,   // ABSENT — measured, see above. NOT unset.
    .gp = kCrt0Gp,
    .libcInit = kCrt0LibcInit,
    .gameMain = kCrt0GameMain, .crt0 = kCrt0Entry,

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
    // crt0 stack-top bias, MEASURED by psxport tools/crt0_extract over this game's own boot
    // executable (SLUS_005.61, entry 0x800DAE8C). `declared = 1` is mandatory: crt0_plan REFUSES a boot when it is 0,
    // because this game's measured bias IS 0 — its crt0 has no bias instruction, which is why the
    // framework's old hardcoded -8 put sp at 0x801FFFF8 instead of 0x80200000. The value NAMES
    // kCrt0StackBias rather than repeating the literal: a second `0` here would be a second copy of a
    // measured value with nothing comparing the two, which is the exact defect that let
    // kCrt0GameMain = 0x80999999 pass every gate. tools/verify_crt0.py --check diffs BOTH members.
    .stackBias = {1, kCrt0StackBias},
};

const GameConfig* x4_game_config() { return &g_x4_cfg; }

// Installs BOTH halves of the seam, because a Core's ctor snapshots them together — installing a
// config without its hooks leaves a Core holding a half-seam.
void x4_install_game_config() {
  extern const GameHooks* x4_game_hooks();   // game/core/game_hooks.cpp
  psxport_install_game(&g_x4_cfg, x4_game_hooks());
}
