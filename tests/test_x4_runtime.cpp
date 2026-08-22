#include "x4_runtime.h"

#include "config_var.h"
#include "config_vars.h"
#include "core.h"
#include "game_iface.h"

#include <cstdio>
#include <memory>
#include <type_traits>

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

  std::puts("X4Runtime: derived install, widescreen-only render policy, no temporal pipeline");
  return 0;
}
