#include "x4_runtime.h"

#include "bios_threads.h"
#include "config_var.h"
#include "config_vars.h"
#include "core.h"
#include "dma_irq.h"
#include "enhancements.h"
#include "fast_wait.h"
#include "game.h"
#include "game_iface.h"
#include "hw_bind.h"
#include "movie_field.h"
#include "stream_startup.h"
#include "widescreen_controller.h"
#include "x4_context.h"
#include "x4_frame_driver.h"

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <type_traits>

void gte_init();

namespace {

GuestProjectionPlan g_projectionPlan;
GuestProjectionGeometry g_projectionGeometry;
uint32_t g_publishedOfx = 0;
uint32_t g_publishedOfy = 0;
uint32_t g_retailBodyCalls = 0;

void mark_retail_body(Core *core) {
  ++g_retailBodyCalls;
  core->r[2] = 0xC0DEC0DEu;
}

GuestProjectionPlan latch_projection(Core *, GuestProjectionGeometry geometry) {
  g_projectionGeometry = geometry;
  return g_projectionPlan;
}

void publish_geom_offset(Core *core) {
  g_publishedOfx = core->r[4];
  g_publishedOfy = core->r[5];
  gte_write_ctrl(24, core->r[4] << 16);
  gte_write_ctrl(25, core->r[5] << 16);
  core->r[4] <<= 16;
  core->r[5] <<= 16;
}

void publish_draw_environment(Core *core) {
  const uint32_t environment = core->r[4];
  core->mem_w16(environment + 0, 17);
  core->mem_w16(environment + 2, 23);
  core->mem_w16(environment + 4, 320);
  core->mem_w16(environment + 6, 239);
  core->mem_w32(environment + 8, 0xA1B2C3D4u);
  core->mem_w32(environment + 12, 0x10293847u);
}

bool verify_widescreen_controller(Core &core) {
  constexpr uint32_t kEnvironment = 0x80110000u;
  constexpr uint32_t kUnrelatedRegister = 0x76543210u;
  constexpr uint32_t kProjectionH = 512u;
  constexpr uint32_t kUv = 0x00445566u;
  constexpr uint32_t kColor = 0x00778899u;
  constexpr uint32_t kOrder = 0x1234u;

  g_projectionPlan = {
      .aspect = PresentationAspect::Wide16x9,
      .nativeExtent = {320, 240},
      .presentationExtent = {428, 240},
      .nativeProjectionExtent = {320, 240},
      .projectionExtent = {428, 240},
      .nativeGuestDrawWidth = 320,
      .guestDrawWidth = 428,
      .presentationHorizontalMargin = 54,
      .projectionHorizontalMargin = 54,
      .projectionCenterX = 214,
      .projectionClipRight = 427,
      .guestClipRight = 427,
  };

  x4::WidescreenController controller(latch_projection);
  core.r[4] = 160;
  core.r[5] = 120;
  core.r[6] = kUnrelatedRegister;
  core.r[8] = kUv;
  core.r[9] = kColor;
  core.r[10] = kOrder;
  gte_write_ctrl(26, kProjectionH);
  controller.publishProjection(core, publish_geom_offset);
  if (g_projectionGeometry.extent.width != 320 || g_projectionGeometry.extent.height != 240 ||
      g_projectionGeometry.drawWidth != 320 || g_publishedOfx != 214 || g_publishedOfy != 120 ||
      gte_read_ctrl(26) != kProjectionH || core.r[6] != kUnrelatedRegister || core.r[8] != kUv || core.r[9] != kColor ||
      core.r[10] != kOrder) {
    std::fprintf(stderr, "widescreen projection changed OFY/H or missed the measured 320x240 publication\n");
    return false;
  }

  core.r[4] = kEnvironment;
  core.r[5] = 0x11112222u;
  core.r[6] = 0x33334444u;
  core.r[7] = 0x55556666u;
  controller.publishDrawEnvironment(core, publish_draw_environment);
  if (core.mem_r16(kEnvironment + 0) != 17 || core.mem_r16(kEnvironment + 2) != 23 ||
      core.mem_r16(kEnvironment + 4) != 428 || core.mem_r16(kEnvironment + 6) != 239 ||
      core.mem_r32(kEnvironment + 8) != 0xA1B2C3D4u || core.mem_r32(kEnvironment + 12) != 0x10293847u ||
      core.r[5] != 0x11112222u || core.r[6] != 0x33334444u || core.r[7] != 0x55556666u || core.r[8] != kUv ||
      core.r[9] != kColor || core.r[10] != kOrder) {
    std::fprintf(stderr, "widescreen draw environment changed data other than the measured RECT.w\n");
    return false;
  }

  // Same guest vertex, projection H, UV, color and ordering produces the same relative screen
  // coordinate; only the title-authored center translates it by the measured plan margin.
  constexpr int kRelativeProjectedX = -37;
  const int standardX = 160 + kRelativeProjectedX;
  const int wideX = controller.plan().projectionCenterX + kRelativeProjectedX;
  if (wideX - standardX != controller.plan().projectionHorizontalMargin) {
    std::fprintf(stderr, "widescreen projection altered central geometry attributes instead of translating OFX\n");
    return false;
  }

  g_projectionPlan = {
      .aspect = PresentationAspect::Standard4x3,
      .nativeExtent = {320, 240},
      .presentationExtent = {320, 240},
      .nativeProjectionExtent = {320, 240},
      .projectionExtent = {320, 240},
      .nativeGuestDrawWidth = 320,
      .guestDrawWidth = 320,
      .projectionCenterX = 160,
      .projectionClipRight = 319,
      .guestClipRight = 319,
  };
  x4::WidescreenController standardController(latch_projection);
  core.r[4] = 160;
  core.r[5] = 120;
  standardController.publishProjection(core, publish_geom_offset);
  core.r[4] = kEnvironment;
  standardController.publishDrawEnvironment(core, publish_draw_environment);
  if (g_publishedOfx != 160 || g_publishedOfy != 120 || core.mem_r16(kEnvironment + 4) != 320) {
    std::fprintf(stderr, "4:3 projection was not an exact 160/320 identity\n");
    return false;
  }

  g_projectionPlan.aspect = PresentationAspect::Wide16x9;
  g_projectionPlan.presentationExtent = {428, 240};
  standardController.synchronizePresentation(core);
  if (standardController.plan().aspect != PresentationAspect::Wide16x9 ||
      standardController.plan().presentationExtent.width != 428) {
    std::fprintf(stderr, "native frame boundary did not re-latch the title presentation mode\n");
    return false;
  }
  return true;
}

bool verify_bios_thread_contract(Core &core) {
  constexpr uint32_t kEntry = 0x8001D064u;
  constexpr uint32_t kStack = 0x801F8100u;
  constexpr uint32_t kGp = 0x8012F418u;
  constexpr uint32_t kMainS0 = 0x13579BDFu;
  constexpr uint32_t kTaskS0 = 0x2468ACE0u;

  x4::bios_threads::Service *service = nullptr;
  uint32_t activeHandle = 0;
  int phase = 0;
  bool taskContextValid = true;
  x4::bios_threads::Service subject(core, [&](Core &taskCore, uint32_t entry) {
    taskContextValid &= entry == kEntry && taskCore.r[29] == kStack && taskCore.r[28] == kGp;
    taskCore.r[16] = kTaskS0;
    phase = 1;
    taskCore.r[4] = x4::bios_threads::kMainThreadHandle;
    taskContextValid &= service->change(x4::bios_threads::kMainThreadHandle);
    taskContextValid &= taskCore.r[16] == kTaskS0;
    taskContextValid &= service->close(activeHandle);
    taskContextValid &= service->open(0x80040000u, kStack - 0x300u, kGp) == UINT32_MAX;
    phase = 2;
  });
  service = &subject;

  core.r[16] = kMainS0;
  const uint32_t first = subject.open(kEntry, kStack, kGp);
  activeHandle = first;
  const uint32_t second = subject.open(0x80020000u, kStack - 0x100u, kGp);
  const uint32_t third = subject.open(0x80030000u, kStack - 0x200u, kGp);
  if (first != x4::bios_threads::Service::handleForSlot(1) || second != x4::bios_threads::Service::handleForSlot(2) ||
      third != x4::bios_threads::Service::handleForSlot(3) ||
      subject.open(0x80040000u, kStack - 0x300u, kGp) != UINT32_MAX) {
    std::fprintf(stderr, "BIOS OpenTh did not allocate exactly the three non-main TCBs\n");
    return false;
  }
  if (!subject.change(first) || phase != 1 || core.r[16] != kMainS0 || !taskContextValid) {
    std::fprintf(stderr, "BIOS ChangeTh did not yield task one back to an intact main context\n");
    return false;
  }
  if (!subject.change(first) || phase != 2 || core.r[16] != kMainS0 || subject.isOpen(first) || !taskContextValid) {
    std::fprintf(stderr, "BIOS ChangeTh did not resume and safely defer the task's self-close\n");
    return false;
  }
  if (subject.change(0xFE000001u) || subject.close(x4::bios_threads::kMainThreadHandle) || subject.close(first)) {
    std::fprintf(stderr, "BIOS thread service accepted an invalid transfer or close\n");
    return false;
  }
  const uint32_t reused = subject.open(kEntry, kStack, kGp);
  if (reused != first) {
    std::fprintf(stderr, "BIOS OpenTh did not reuse the first closed TCB slot\n");
    return false;
  }
  return subject.close(reused) && subject.close(second) && subject.close(third);
}

bool verify_title_movie_field_yield(Core &core) {
  constexpr uint32_t kEntry = 0x8001D064u;
  constexpr uint32_t kStack = 0x801F8100u;
  constexpr uint32_t kGp = 0x8012F418u;
  x4::bios_threads::Service *service = nullptr;
  uint32_t activeHandle = 0;
  int phase = 0;
  bool valid = true;
  x4::bios_threads::Service subject(core, [&](Core &taskCore, uint32_t entry) {
    valid &= entry == kEntry;
    taskCore.r[31] = 0x80018BC4u;
    phase = 1;
    x4::movie::yieldField(taskCore, 0x80018BC4u, *service);
    valid &= taskCore.r[2] == 0u;
    phase = 2;
    valid &= service->close(activeHandle);
  });
  service = &subject;
  activeHandle = subject.open(kEntry, kStack, kGp);
  if (!subject.change(activeHandle) || phase != 1 || !valid) {
    std::fprintf(stderr, "title movie field did not park the retail task fiber\n");
    return false;
  }
  if (!subject.change(activeHandle) || phase != 2 || subject.isOpen(activeHandle) || !valid) {
    std::fprintf(stderr, "title movie field did not resume the preserved retail task stack\n");
    return false;
  }
  return true;
}

bool verify_title_stream_field_yield(Core &core) {
  constexpr uint32_t kEntry = 0x80018788u;
  constexpr uint32_t kStack = 0x801F8100u;
  constexpr uint32_t kGp = 0x8012F418u;
  x4::bios_threads::Service *service = nullptr;
  uint32_t activeHandle = 0;
  int phase = 0;
  bool valid = true;
  x4::bios_threads::Service subject(core, [&](Core &taskCore, uint32_t entry) {
    valid &= entry == kEntry;
    phase = 1;
    x4::stream_startup::awaitField(taskCore, *service);
    phase = 2;
    valid &= service->close(activeHandle);
  });
  service = &subject;
  activeHandle = subject.open(kEntry, kStack, kGp);
  if (!subject.change(activeHandle) || phase != 1 || !valid) {
    std::fprintf(stderr, "title stream field did not park the retail task fiber\n");
    return false;
  }
  if (!subject.change(activeHandle) || phase != 2 || subject.isOpen(activeHandle) || !valid) {
    std::fprintf(stderr, "title stream field did not resume the preserved retail task stack\n");
    return false;
  }
  return true;
}

bool verify_synchronous_loader_leaves(Core &core) {
  constexpr uint32_t kDestination = 0x80110080u;
  constexpr uint32_t kResult = 0x801100C0u;
  x4::fast_wait::State &load = x4::context(core).fastWait;

  load.phase = x4::fast_wait::Phase::Inactive;
  g_retailBodyCalls = 0;
  x4::fast_wait::cd_ready(&core, mark_retail_body);
  if (g_retailBodyCalls != 1 || core.r[2] != 0xC0DEC0DEu) {
    std::fprintf(stderr, "inactive synchronous-loader leaf did not call the original retail body\n");
    return false;
  }

  load.phase = x4::fast_wait::Phase::Preparing;
  core.r[4] = 1;
  x4::fast_wait::cd_ready(&core, mark_retail_body);
  if (core.r[2] != 0) {
    std::fprintf(stderr, "preparing synchronous loader reported a ready sector\n");
    return false;
  }
  core.r[4] = 6;
  x4::fast_wait::cd_ready(&core, mark_retail_body);
  if (core.r[2] != 1) {
    std::fprintf(stderr, "synchronous loader did not complete the measured Setloc-ready query\n");
    return false;
  }
  core.r[4] = 0x0E;
  x4::fast_wait::cd_control(&core, mark_retail_body, false);
  if (core.r[2] != 1) {
    std::fprintf(stderr, "synchronous loader rejected the measured Setmode command\n");
    return false;
  }
  core.r[4] = 1;
  core.r[6] = kResult;
  core.mem_w8(kResult, 0xFFu);
  x4::fast_wait::cd_control(&core, mark_retail_body, true);
  if (core.r[2] != 1 || core.mem_r8(kResult) != 0x02u) {
    std::fprintf(stderr, "synchronous loader did not return the measured standby/no-shell status\n");
    return false;
  }

  for (size_t byte = 0; byte < load.rawSector.size(); ++byte) {
    load.rawSector[byte] = static_cast<uint8_t>(byte);
  }
  load.phase = x4::fast_wait::Phase::Delivering;
  g_retailBodyCalls = 0;
  load.sectorCursor = 12;
  core.r[4] = kDestination;
  core.r[5] = 3;
  x4::fast_wait::cd_get_sector(&core, mark_retail_body);
  if (core.r[2] != 1 || load.sectorCursor != 24) {
    std::fprintf(stderr, "synchronous loader did not consume the measured three-word raw header\n");
    return false;
  }
  for (uint32_t byte = 0; byte < 12; ++byte) {
    if (core.mem_r8(kDestination + byte) != static_cast<uint8_t>(byte + 12)) {
      std::fprintf(stderr, "synchronous loader copied from the wrong raw-sector cursor\n");
      return false;
    }
  }
  core.r[4] = 1;
  x4::fast_wait::cd_ready(&core, mark_retail_body);
  if (core.r[2] != 1) {
    std::fprintf(stderr, "delivering synchronous loader did not report a ready sector\n");
    return false;
  }

  load.phase = x4::fast_wait::Phase::Inactive;
  x4::cv_fastwait.set(psx::config::Layer::Runtime, true);
  const uint64_t removedBefore = load.loadingPresentationsRemoved;
  g_retailBodyCalls = 0;
  x4::fast_wait::loading_presentation_wait(&core, mark_retail_body);
  if (g_retailBodyCalls != 0 || load.loadingPresentationsRemoved != removedBefore + 1) {
    std::fprintf(stderr, "enabled fast loading ran the retail loading-presentation task\n");
    return false;
  }
  x4::cv_fastwait.set(psx::config::Layer::Runtime, false);
  x4::fast_wait::loading_presentation_wait(&core, mark_retail_body);
  x4::cv_fastwait.clear(psx::config::Layer::Runtime);
  if (g_retailBodyCalls != 1) {
    std::fprintf(stderr, "disabled fast loading did not call the original retail presentation task\n");
    return false;
  }
  return true;
}

} // namespace

int main() {
  static_assert(std::is_base_of_v<GameRuntime, x4::X4Runtime>);
  static_assert(!std::is_base_of_v<LegacyGameRuntimeAdapter, x4::X4Runtime>);

  x4::X4Runtime runtime;
  const RenderCapabilities capabilities = runtime.renderCapabilities();
  if (capabilities.defaultPath != RenderPath::Gte || capabilities.nativeRenderPath ||
      capabilities.temporalInterpolation || !capabilities.supports(RenderPath::Gte) ||
      !capabilities.supports(RenderPath::Psx) || capabilities.supports(RenderPath::Native) ||
      !capabilities.playerSelectable(RenderPath::Gte) || capabilities.playerSelectable(RenderPath::Psx) ||
      capabilities.playerSelectable(RenderPath::Native) || capabilities.playerPathCount() != 1 ||
      render_path_resolve(RenderPath::Native, capabilities) != RenderPath::Gte) {
    std::fprintf(stderr, "X4Runtime exposed a renderer or temporal product outside its guest-wide policy\n");
    return 1;
  }

  psx::config::cv_fps60.set(psx::config::Layer::Value, true);
  psxport_install_game(runtime);
  auto game = std::make_unique<Game>();
  psx::config::cv_fps60.clear(psx::config::Layer::Value);
  if (game->mods.temporalInterpolationSupported() || game->mods.fps60 != 0) {
    std::fprintf(stderr, "X4Runtime allowed the settings layer to arm synthetic interpolation\n");
    return 1;
  }
  Core *core = &game->core;
  gte_init();
  gte_bind(core);
  const GameHooks *legacyHooks = runtime.legacyHooksForMigration();
  const GameConfig *legacyConfig = runtime.legacyConfigForMigration();
  const GuestProgramImage *programImage = runtime.guestProgramImage();
  const GuestPadBufferLayout *padLayout = runtime.guestPadBufferLayout();
  if (psxport_game_runtime() != &runtime || core->runtime != &runtime || game->runtime != &runtime ||
      legacyConfig == nullptr || legacyHooks == nullptr || programImage == nullptr || padLayout == nullptr ||
      padLayout->slot0Buffer != 0x80166D68u || padLayout->slot1Buffer != 0x8012F46Cu ||
      padLayout->slotPointerTable != 0u || programImage->gameMainEntry != 0x80012024u ||
      programImage->residentText.begin != 0x00010000u || programImage->residentText.end != 0x0012F800u) {
    std::fprintf(stderr, "X4Runtime did not own the installed compatibility seam\n");
    return 1;
  }
  if (legacyConfig->dmaCallbackTable != x4::stream_startup::kDmaCallbackTable ||
      dma_callback_slot(legacyConfig->dmaCallbackTable, 3) != x4::stream_startup::kDmaChannel3CallbackSlot) {
    std::fprintf(stderr, "X4Runtime did not publish the measured per-channel DMA callback table\n");
    return 1;
  }
  if (legacyHooks->bootInit != nullptr || legacyHooks->registerOverrides != nullptr ||
      legacyHooks->fps60ReadSceneCam != nullptr || legacyHooks->fps60WorldPass != nullptr ||
      legacyHooks->fps60BbSwapPrev != nullptr || legacyHooks->fps60TemporalRotate != nullptr) {
    std::fprintf(stderr, "boot, override, or temporal ownership remained in legacy GameHooks\n");
    return 1;
  }
  if (game->temporalPresentation != nullptr || game->frameDriver == nullptr ||
      runtime.guestWidescreenProjection() == nullptr) {
    std::fprintf(stderr, "X4Runtime omitted its frame driver/widescreen policy or constructed temporal history\n");
    return 1;
  }
  if (runtime.guestVramIsPicture(*game) || game_guest_vram_is_picture(*game)) {
    std::fprintf(stderr, "X4Runtime treated idle persistent guest VRAM as a second picture owner\n");
    return 1;
  }
  game->cd.stream_active = 1;
  if (!runtime.guestVramIsPicture(*game) || !game_guest_vram_is_picture(*game)) {
    std::fprintf(stderr, "X4Runtime did not transfer picture ownership to the active STR stream\n");
    return 1;
  }
  game->cd.stream_active = 0;

  x4::cv_widescreen.set(psx::config::Layer::Runtime, false);
  if (runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Standard4x3) {
    std::fprintf(stderr, "disabled widescreen did not preserve the exact 4:3 policy\n");
    return 1;
  }
  x4::cv_widescreen.set(psx::config::Layer::Runtime, true);
  if (runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Wide16x9) {
    std::fprintf(stderr, "enabled widescreen did not select the 16:9 guest projection\n");
    return 1;
  }
  game->cd.stream_active = 1;
  if (runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Standard4x3) {
    std::fprintf(stderr, "active 24-bit STR movie did not preserve its authored 4:3 picture\n");
    return 1;
  }
  game->cd.stream_active = 0;
  if (runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Wide16x9) {
    std::fprintf(stderr, "widescreen gameplay did not resume after the STR stream stopped\n");
    return 1;
  }
  {
    psx::config::ScopedDiagnosticRun comparison(psx::config::DiagnosticRunMode::CompareCandidate);
    if (runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Standard4x3) {
      std::fprintf(stderr, "comparison run did not suppress the guest-state widescreen enhancement\n");
      return 1;
    }
  }
  x4::cv_widescreen.clear(psx::config::Layer::Runtime);

  if (!verify_widescreen_controller(*core)) {
    return 1;
  }
  if (!verify_bios_thread_contract(*core)) {
    return 1;
  }
  if (!verify_title_movie_field_yield(*core)) {
    return 1;
  }
  if (!verify_title_stream_field_yield(*core)) {
    return 1;
  }
  if (!verify_synchronous_loader_leaves(*core)) {
    return 1;
  }

  x4::context(*core).movieCleanup.begin();
  x4::cv_widescreen.set(psx::config::Layer::Runtime, true);
  if (!runtime.guestVramIsPicture(*game) || !game_guest_vram_is_picture(*game) ||
      runtime.guestWidescreenProjection()->presentationAspect(*core) != PresentationAspect::Standard4x3) {
    std::fprintf(stderr, "movie cleanup dropped or widened the final STR picture during its retained fields\n");
    return 1;
  }
  x4::cv_widescreen.clear(psx::config::Layer::Runtime);

  std::puts("X4Runtime: derived install, retail BIOS threads, synchronous loading leaves, widescreen-only policy, no "
            "temporal pipeline");
  return 0;
}
