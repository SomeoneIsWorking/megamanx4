#include "x4_runtime.h"

#include "bios_threads.h"
#include "config_var.h"
#include "config_vars.h"
#include "core.h"
#include "game_iface.h"

#include <cstdio>
#include <memory>
#include <type_traits>

namespace {

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

} // namespace

int main() {
  static_assert(std::is_base_of_v<GameRuntime, x4::X4Runtime>);
  static_assert(std::is_base_of_v<LegacyGameRuntimeAdapter, x4::X4Runtime>);

  if (x4::X4Runtime::requiredRenderPath() != RenderPath::Gte || !x4::X4Runtime::supportsRenderPath(RenderPath::Gte) ||
      !x4::X4Runtime::supportsRenderPath(RenderPath::Psx) || x4::X4Runtime::supportsRenderPath(RenderPath::Native)) {
    std::fprintf(stderr, "X4Runtime accepted a producer-only picture path\n");
    return 1;
  }
  static_assert(x4::X4Runtime::executableId() == "SLUS_005.61");
  static_assert(x4::X4Runtime::targetsWidescreen());
  static_assert(!x4::X4Runtime::supportsTemporalInterpolation());
  static_assert(!x4::X4Runtime::requiresNativeDepth());
  static_assert(!x4::X4Runtime::requiresNativeProducers());

  x4::X4Runtime runtime;
  if (!runtime.configureRenderPath() || psx::config::render_path() != RenderPath::Gte) {
    std::fprintf(stderr, "X4Runtime did not install the guest-picture default\n");
    return 1;
  }
  psx::config::cv_render_path.set(psx::config::Layer::Runtime, "native");
  if (runtime.configureRenderPath()) {
    std::fprintf(stderr, "X4Runtime accepted the explicit producer-only path\n");
    return 1;
  }
  psx::config::cv_render_path.clear(psx::config::Layer::Runtime);

  if (!runtime.validateRenderEnhancements()) {
    std::fprintf(stderr, "X4Runtime rejected its neutral no-interpolation default\n");
    return 1;
  }
  psx::config::cv_fps60.set(psx::config::Layer::Value, true);
  if (runtime.validateRenderEnhancements()) {
    std::fprintf(stderr, "X4Runtime accepted synthetic temporal interpolation\n");
    return 1;
  }
  psx::config::cv_fps60.clear(psx::config::Layer::Value);

  psxport_install_game(runtime);
  auto core = std::make_unique<Core>();
  const GameHooks *legacyHooks = runtime.legacyHooksForMigration();
  if (psxport_game_runtime() != &runtime || core->runtime != &runtime ||
      runtime.legacyConfigForMigration() == nullptr || legacyHooks == nullptr) {
    std::fprintf(stderr, "X4Runtime did not own the installed compatibility seam\n");
    return 1;
  }
  if (legacyHooks->bootInit != nullptr || legacyHooks->registerOverrides != nullptr ||
      legacyHooks->fps60ReadSceneCam != nullptr || legacyHooks->fps60WorldPass != nullptr ||
      legacyHooks->fps60BbSwapPrev != nullptr || legacyHooks->fps60TemporalRotate != nullptr) {
    std::fprintf(stderr, "boot, override, or temporal ownership remained in legacy GameHooks\n");
    return 1;
  }
  if (!verify_bios_thread_contract(*core)) {
    return 1;
  }

  std::puts("X4Runtime: derived install, retail BIOS threads, widescreen-only policy, no temporal pipeline");
  return 0;
}
