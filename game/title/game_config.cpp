// game_config.cpp - measured SLUS_005.61 (USA) facts for framework code still reading GameConfig.
// A field stays zero until measured from these bytes; a zero the framework needs fails fast.
#include "bios_threads.h"
#include "guest_program_image.h"
#include "legacy_game_config.h"
#include "legacy_game_interface.h"
#include "pad_layout.h"
#include "stream_startup.h"
#include "vsync_sync.h"

namespace x4::legacy {
namespace {

// PS-EXE header and SYSTEM.CNF values of SLUS_005.61 (sha1 213733031136d095ca275d6957695aa25011cfa5).
// d_addr/d_size and b_addr/b_size are 0: the game clears its own BSS.
static constexpr uint32_t kPsExeEntry = 0x800DAE8Cu;    // header pc0
static constexpr uint32_t kPsExeTextAddr = 0x80010000u; // header t_addr
static constexpr uint32_t kPsExeTextSize = 0x0011F800u; // header t_size
static_assert(kPsExeEntry >= kPsExeTextAddr && kPsExeEntry < kPsExeTextAddr + kPsExeTextSize,
              "the PS-EXE entry must lie inside the loaded text — if this fires, the header was "
              "misread and every number in this file's comment block is suspect");

// crt0 at pc0, checked against the image by the runtime crt0_audit at every boot: .bss
// 0x8012F418..0x80175F38, stack top 0x00200000 from [0x800DAF3C], heap base 0x80175F38 size 0x820C8,
// gp = 0x8012F418, BIOS A(39h) InitHeap thunk 0x800EDCDC, then `jal 0x80012024`.
static constexpr uint32_t kCrt0BssZeroLo = 0x8012F418u;
static constexpr uint32_t kCrt0BssZeroHi = 0x80175F38u;
static constexpr uint32_t kCrt0StackTopBase = 0x800DAF3Cu;
static constexpr uint32_t kCrt0StackTopBas2 = 0x8011CB74u;
static constexpr uint32_t kCrt0HeapBase = 0x80175F38u;
static constexpr uint32_t kCrt0Gp = 0x8012F418u;
static constexpr uint32_t kCrt0LibcInit = 0x800EDCDCu; // BIOS A(39h) InitHeap thunk
static constexpr uint32_t kCrt0GameMain = 0x80012024u;
static constexpr uint32_t kCrt0Entry = kPsExeEntry; // crt0 IS the PS-EXE entry
// No `addi v0,v0,-8` bias between the stack-top load and `or sp`, so the bias is 0.
static constexpr int32_t kCrt0StackBias = 0;
static_assert(kCrt0BssZeroHi - kCrt0BssZeroLo == 0x46B20u,
              "the measured .bss size must stay 0x46B20 — if this fires, the clear-loop bounds were "
              "re-derived to something else and the authenticated executable must be measured again");
static_assert(kCrt0HeapBase == kCrt0BssZeroHi,
              "this crt0 starts the heap exactly at the end of .bss; a divergence means one of the "
              "two was mis-derived");
static_assert(kCrt0Gp == kCrt0BssZeroLo,
              "gp points at the base of .bss in this crt0 (and the ra it saves at gp+0 is bss[0])");
static_assert(kCrt0BssZeroHi > kPsExeTextAddr + kPsExeTextSize,
              ".bss must END above the loaded text image — a .bss entirely inside .text would mean "
              "the clear loop wipes code, i.e. the bounds were misread");
// .bss starts 0x3E8 bytes below the end of the sector-padded text; those overlapping file bytes are all zero.
static_assert(kCrt0BssZeroLo < kPsExeTextAddr + kPsExeTextSize,
              "if .bss no longer starts inside the sector-padded text tail, the note above about the "
              "1000 zero bytes of overlap is stale and must be re-measured");

const GuestProgramImage g_x4_program_image = {
    .bss = {kCrt0BssZeroLo, kCrt0BssZeroHi},
    .stackTopWordAddress = kCrt0StackTopBase,
    .stackReserveWordAddress = kCrt0StackTopBas2,
    .heapBase = kCrt0HeapBase,
    .heapSizeStoreAddress = 0,
    .heapBaseStoreAddress = 0,
    .globalPointer = kCrt0Gp,
    .libcInitEntry = kCrt0LibcInit,
    .gameMainEntry = kCrt0GameMain,
    .crt0Entry = kCrt0Entry,
    .residentText = {kPsExeTextAddr & 0x1FFFFFFFu, (kPsExeTextAddr + kPsExeTextSize) & 0x1FFFFFFFu},
    .backtraceText = {},
    .stackBias = {true, kCrt0StackBias},
};

static_assert(x4::vsync::kVblankCounter == 0x8011DC50u,
              "the libetc VBlank counter is read from SLUS_005.61, not chosen; if this fires, "
              "re-measure it and the owner in game/frame/vsync_sync.cpp with it");
static_assert(x4::vsync::kVSyncEntryEnd - x4::vsync::kVSync == 4u,
              "the trap window is the measured four-byte libetc VSync entry and nothing else; a "
              "wider window would admit adjacent library code into the host-service table");

// Designated initializers so appended framework fields cannot rebind values; keep declaration order.
const GameConfig g_x4_cfg = {
    // crt0 / boot (heapSizePtr/heapBasePtr are absent in this crt0)
    .bssZeroLo = kCrt0BssZeroLo,
    .bssZeroHi = kCrt0BssZeroHi,
    .stackTopBase = kCrt0StackTopBase,
    .stackTopBase2 = kCrt0StackTopBas2,
    .heapBase = kCrt0HeapBase,
    .heapSizePtr = 0,
    .heapBasePtr = 0,

    .gp = kCrt0Gp,
    .libcInit = kCrt0LibcInit,
    .gameMain = kCrt0GameMain,
    .crt0 = kCrt0Entry,

    // disc key (port fact)
    .discEnvVar = "PSXPORT_X4_DISC",

    // The guest plays its own movies.
    .bootFmv = {nullptr, nullptr, nullptr, nullptr},

    // Native-producer frame path only; X4FrameDriver calls the retail GTE/OT leaves, so zero.
    .otRegionBase = 0,
    .otRegionStride = 0,
    .packetPoolBase = 0,
    .packetPoolStride = 0,
    .otBasePtr = 0,
    .dwellCounter = 0,
    .poolPtrCur = 0,
    .poolPtrLast = 0,
    .clearOtagR = 0,
    .putDrawEnv = 0,
    .drawSync = 0,
    .irqEventClasses = {0, 0, 0},
    // Scheduler hooks are fail-fast, so nothing reads these.
    .taskTableBase = 0,
    .taskSlotStride = 0,
    .taskCount = 0,
    .curTaskPtr = 0,
    .stageStart = 0,
    .stageDemo = 0,
    .stageGame = 0,

    // No overlays: the boot executable is the whole engine.
    .overlaySlots = {{0, nullptr}, {0, nullptr}, {0, nullptr}},

    // The retail libcd route via CD callback 0x800E7944 stays live, so no HLE replacements.
    .cdInit = 0,
    .cdCommand = 0,
    .cdSync = 0,
    .cdReadPrim = 0,
    .cdFileLoad = 0,
    .cdAsyncRead = 0,
    .voicePlay = 0,
    .voiceStop = 0,
    .lastSectorTracker = 0,
    .cdInlineLoad = 0,
    .cdCmdStream = 0,
    .cdCallbackTable = {0, 0, 0, 0},
    .cdCallbackFn = {0, 0, 0, 0},
    .cdGetSector = 0,
    .cdReadyCbPtr = 0,
    .cdLastPosBuf = 0,
    .cdReadStock = 0,
    .cdReadSync = 0,
    .cdSearchFile = 0,
    // FUN_800E59A0 (DMACallback) indexes this table; STR installs its DMA3 completion at 0x8011DC68.
    .dmaCallbackTable = x4::stream_startup::kDmaCallbackTable,

    // pad driver; slot 1 is only the input half of co-op
    .padSlot0Buf = x4::pad::kSlot0Buffer,
    .padSlot1Buf = x4::pad::kSlot1Buffer,
    .padDriverFn = 0,
    .padSlotPtrTable = 0,
    .padSlotPtrStride = 0,

    // Exact libetc VSync entry and BIOS thread thunk windows; the title serves 0x800E4DB0 through
    // x4::vsync::serveVSync, and its VBlank counter query is answered there (no field for it here).
    .hle = {.windowLo = {x4::vsync::kVSync, x4::bios_threads::kOpenThread},
            .windowHi = {x4::vsync::kVSyncEntryEnd, x4::bios_threads::kThreadWindowEnd},
            .vsyncTrap = x4::vsync::kVSync},

    // Retired mirror; the shipping policy is X4Runtime::guestVramIsPicture().
    .preserveVramBackdrop = 0,

    .cardEnvVar = "PSXPORT_X4_CARD",
    .cardDefaultPath = "scratch/saves/megamanx4.mcr",

    // One pacing call per display field.
    .paceQuota = 1,

    .windowTitle = "Mega Man X4 (psxport)",
    // declared = 1: crt0_plan refuses an undeclared bias of 0.
    .stackBias = {1, kCrt0StackBias},
};

} // namespace

const GameConfig &measuredConfig() {
  return g_x4_cfg;
}

const GuestProgramImage &measuredProgramImage() {
  return g_x4_program_image;
}

} // namespace x4::legacy
