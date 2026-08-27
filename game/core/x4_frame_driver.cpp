#include "x4_frame_driver.h"

#include "core.h"
#include "game.h"
#include "vsync_sync.h"

namespace x4::frame {
namespace {

// Retail SLUS_005.61 gameMain 0x80012024, measured from generated/shard_4.c and independently
// readable in external/mmx4/src/main/2824.c. These are entry points and guest globals, not native
// replacements: every called body remains generated and dispatchable through the ordinary seam.
constexpr std::uint32_t kStartup = 0x800DAE84u;
constexpr std::uint32_t kInitialize = 0x8001213Cu;
constexpr std::uint32_t kPutDispEnv = 0x800EAAD8u;
constexpr std::uint32_t kPutDrawEnv = 0x800EA880u;
constexpr std::uint32_t kDrawOTag = 0x800EA80Cu;
constexpr std::uint32_t kClearOTagR = 0x800EA714u;
constexpr std::uint32_t kBeforeObjectsA = 0x800168D8u;
constexpr std::uint32_t kBeforeObjectsB = 0x800169D8u;
constexpr std::uint32_t kRoutePads = 0x80012328u;
constexpr std::uint32_t kClearVramRectPointers = 0x80015E0Cu;
constexpr std::uint32_t kUpdateTasks = 0x80012600u;
constexpr std::uint32_t kDrainArchive = 0x80014780u;
constexpr std::uint32_t kDrawSync = 0x800EA20Cu;
constexpr std::uint32_t kLoadVramRectPointers = 0x80015E54u;
constexpr std::uint32_t kLoadPalette = 0x80016004u;
constexpr std::uint32_t kFinishFrame = 0x80012454u;

constexpr std::uint32_t kScratchDrawInfoPosition = 0x1F800000u;
constexpr std::uint32_t kCurrentDrawInfo = 0x80142F80u;
constexpr std::uint32_t kDrawInfos = 0x80166C10u;
constexpr std::uint32_t kFieldCounter = 0x80141BD8u;
constexpr std::uint32_t kDrawInfoStride = 160u;
constexpr std::uint32_t kDrawEnvOffset = 20u;
constexpr std::uint32_t kOrderingTableClearOffset = 112u;
constexpr std::uint32_t kOrderingTableDrawOffset = 156u;

void call(Core &core, GuestDispatch dispatch, std::uint32_t entry, std::uint32_t returnAddress, std::uint32_t ticks) {
  core.r[31] = returnAddress;
  rec_guest_instruction_ticks(&core, ticks);
  dispatch(&core, entry);
}

bool movieOwnsPicture(const Core &core) {
  return core.game && core.game->cd.stream_active != 0;
}

void runRetailFramePrefix(Core &core, GuestDispatch dispatch) {
  std::uint32_t drawInfo = core.mem_r32(kCurrentDrawInfo);
  core.r[4] = drawInfo;
  call(core, dispatch, kPutDispEnv, 0x80012060u, 4u);

  drawInfo = core.mem_r32(kCurrentDrawInfo);
  core.r[4] = drawInfo + kDrawEnvOffset;
  call(core, dispatch, kPutDrawEnv, 0x80012070u, 4u);

  drawInfo = core.mem_r32(kCurrentDrawInfo);
  core.r[4] = drawInfo + kOrderingTableDrawOffset;
  call(core, dispatch, kDrawOTag, 0x80012080u, 4u);

  gte_hold_src(&core, 5, kScratchDrawInfoPosition);
  const std::uint32_t drawInfoPosition = core.mem_r32(kScratchDrawInfoPosition) ^ 1u;
  drawInfo = kDrawInfos + drawInfoPosition * kDrawInfoStride;
  core.mem_w32(kScratchDrawInfoPosition, drawInfoPosition);
  gte_copy_pz(&core, 5, kScratchDrawInfoPosition);
  core.mem_w32(kCurrentDrawInfo, drawInfo);
  core.r[4] = drawInfo + kOrderingTableClearOffset;
  core.r[5] = 12u;
  call(core, dispatch, kClearOTagR, 0x800120B8u, 14u);

  call(core, dispatch, kBeforeObjectsA, 0x800120C0u, 2u);
  call(core, dispatch, kBeforeObjectsB, 0x800120C8u, 2u);
  call(core, dispatch, kRoutePads, 0x800120D0u, 2u);
  call(core, dispatch, kClearVramRectPointers, 0x800120D8u, 2u);

  core.mem_w32(kFieldCounter, core.mem_r32(kFieldCounter) + 1u);
}

void runRetailFrameSuffix(Core &core, GuestDispatch dispatch) {
  call(core, dispatch, kDrainArchive, 0x800120F4u, 2u);

  core.r[4] = 0u;
  call(core, dispatch, kDrawSync, 0x800120FCu, 2u);
  call(core, dispatch, kLoadVramRectPointers, 0x80012104u, 2u);
  call(core, dispatch, kLoadPalette, 0x8001210Cu, 2u);
  core.r[4] = 0u;
  call(core, dispatch, kDrawSync, 0x80012114u, 2u);
  call(core, dispatch, kFinishFrame, 0x8001211Cu, 2u);
}

} // namespace

void bootPrefix(Core &core, GuestDispatch dispatch) {
  // Preserve the retail main frame on the guest stack. Although the host frame shell owns the
  // repetition, callees and backtraces must see the same never-returned gameMain activation.
  core.r[29] -= 32u;
  core.mem_w32(core.r[29] + 24u, core.r[31]);
  core.mem_w32(core.r[29] + 20u, core.r[17]);
  core.mem_w32(core.r[29] + 16u, core.r[16]);

  call(core, dispatch, kStartup, 0x80012038u, 5u);
  core.r[17] = kScratchDrawInfoPosition;
  call(core, dispatch, kInitialize, 0x80012040u, 2u);
  core.r[16] = kFieldCounter;
}

void bootPrefix(Core &core) {
  bootPrefix(core, rec_dispatch);
}

X4FrameDriver::X4FrameDriver(GuestDispatch dispatch, FieldService fieldService, PresentationSync presentationSync)
    : dispatch_(dispatch), fieldService_(fieldService), presentationSync_(presentationSync) {}

X4FrameDriver::X4FrameDriver() : X4FrameDriver(rec_dispatch, vsync::deliverField) {}

void X4FrameDriver::stepFrame(Core &core, std::uint32_t) {
  // The generated loop's back-edge/prologue reaches this call boundary after two guest
  // instructions. Preserve its deterministic instruction clock before delivering pending work.
  rec_guest_instruction_ticks(&core, 2u);
  if (core.pending_work) {
    rec_irq_poll(&core);
  }

  if (presentationSync_) {
    presentationSync_(core);
  }

  // This replaces only retail VSync(0). The boundary advances the CURRENT class-0 handler (including
  // libsnd's chained tick), pad, SPU, snapshot, presentation and pacing exactly once. Any actual call
  // to libetc VSync now reaches the full-entry trap declared by the title.
  core.r[31] = 0x80012050u;
  core.r[4] = 0u;
  rec_guest_instruction_ticks(&core, 2u);
  fieldService_(core);

  // The retail movie call blocks inside UpdateTasks across its VSync boundaries; the outer main
  // loop does not restart its 16-bit gameplay draw prefix while that call is suspended. Replaying
  // the prefix erased words 0..319 of a 480-word 24-bit MDEC buffer, leaving exactly its rightmost
  // third. Resume only the blocked task transaction until the movie releases the continuous stream.
  if (!movieOwnsPicture(core)) {
    runRetailFramePrefix(core, dispatch_);
  }
  call(core, dispatch_, kUpdateTasks, 0x800120ECu, 5u);
  if (movieOwnsPicture(core)) {
    return;
  }
  runRetailFrameSuffix(core, dispatch_);
}

} // namespace x4::frame
