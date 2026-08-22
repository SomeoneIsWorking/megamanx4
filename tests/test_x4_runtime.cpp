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

  psxport_install_game(runtime);
  auto core = std::make_unique<Core>();
  const GameHooks *legacyHooks = runtime.legacyHooksForMigration();
  if (psxport_game_runtime() != &runtime || core->runtime != &runtime ||
      runtime.legacyConfigForMigration() == nullptr || legacyHooks == nullptr) {
    std::fprintf(stderr, "X4Runtime did not own the installed compatibility seam\n");
    return 1;
  }
  if (legacyHooks->bootInit != nullptr || legacyHooks->registerOverrides != nullptr) {
    std::fprintf(stderr, "boot or override ownership remained in legacy GameHooks\n");
    return 1;
  }

  std::puts("X4Runtime: derived install, measured legacy facts, owned boot/override/render policy");
  return 0;
}
