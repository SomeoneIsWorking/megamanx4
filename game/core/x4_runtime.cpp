#include "x4_runtime.h"

#include "cfg.h"
#include "config_var.h"
#include "config_vars.h"
#include "core.h"
#include "game.h"
#include "legacy_game_interface.h"
#include "vsync_sync.h"

#include <lucent/log.h>

#include <cstdlib>

namespace x4 {

X4Runtime::X4Runtime() : LegacyGameRuntimeAdapter(legacy::measuredConfig, legacy::compatibilityHooks) {}

bool X4Runtime::configureRenderPath() {
  // Change only the framework default. A persisted setting, launch override, or runtime selection
  // still outranks it through the normal CVar ladder and is validated below.
  psx::config::cv_render_path.set(psx::config::Layer::Default, render_path_name(requiredRenderPath()));

  const RenderPath selected = psx::config::render_path();
  if (!supportsRenderPath(selected)) {
    lucent::error("x4-render",
                  "render path '{}' is unsupported: Mega Man X4 has no PC-native producers. "
                  "Select 'gte' for the guest picture or 'psx' for the software-rasterized reference.",
                  render_path_name(selected));
    return false;
  }
  return true;
}

bool X4Runtime::validateRenderEnhancements() const {
  if (!supportsTemporalInterpolation() && psx::config::cv_fps60.get()) {
    lucent::error("x4-render",
                  "PSXPORT_FPS60 requests interpolated frames, but Mega Man X4 ({}) already runs at "
                  "the target 60 Hz cadence. Clear PSXPORT_FPS60/fps60=1; X4's render enhancement "
                  "is widescreen only and does not use temporal interpolation, native depth, or "
                  "PC-native producers (resolved at {} layer).",
                  executableId(),
                  psx::config::layer_name(psx::config::cv_fps60.layer()));
    return false;
  }
  return true;
}

void X4Runtime::registerOverrides(Game &game) {
  // RE-11 owns only libetc's measured wait helper. The retail VSync body and IRQ-0 handler remain
  // recompiled guest code; vsync_sync restores the missing asynchronous producer between them.
  vsync::install(&game);
}

void X4Runtime::bootInit(Core &core) {
  const GameConfig *config = legacyConfigForMigration();
  if (!config || !config->gameMain) {
    cfg_loge("boot",
             "the measured RE-01 gameMain entry is absent from X4's legacy program facts; refusing "
             "to dispatch address 0");
    std::abort();
  }
  cfg_logi("boot", "dispatching guest main() 0x%08X on the recompiled substrate", config->gameMain);
  rec_dispatch(&core, config->gameMain);
}

} // namespace x4
