#include "x4_runtime.h"

#include "bios_threads.h"
#include "cfg.h"
#include "core.h"
#include "game.h"
#include "legacy_game_interface.h"
#include "recomp_register.h"
#include "title_quad.h"
#include "vsync_sync.h"
#include "x4_context.h"

#include <cstdlib>

namespace x4 {

X4Runtime::X4Runtime() {
  // Compatibility views remain available to unmigrated generic framework algorithms, but behavior
  // and typed executable facts are owned by this direct derived runtime. In particular, no legacy
  // adapter vtable is linked, so its Fps60 factory cannot drag interpolation into this 60 Hz title.
  bindLegacyInterface(&legacy::measuredConfig, &legacy::compatibilityHooks);
}

void *X4Runtime::createContext(Core &core) {
  return new X4Context(core);
}

void X4Runtime::destroyContext(void *context) {
  delete static_cast<X4Context *>(context);
}

void X4Runtime::registerOverrides(Game &game) {
  // RE-11 owns only libetc's measured wait helper. The retail VSync body and IRQ-0 handler remain
  // recompiled guest code; vsync_sync restores the missing asynchronous producer between them.
  vsync::install(&game);
  bios_threads::install(game);
  title_quad::registerOverride();
  x4_install_projection_overrides();
  // The loading-coroutine conversion (RE-09 job B): the two measured retail wait bodies, wrapped by
  // the super-call seam so PSXPORT_X4_FASTWAIT can withhold their presentation without touching a
  // byte of their mechanics.
  x4_install_loading_overrides();
}

void X4Runtime::bootInit(Core &core) {
  const GuestProgramImage *image = guestProgramImage();
  if (!image || !image->gameMainEntry) {
    cfg_loge("boot",
             "the measured RE-01 gameMain entry is absent from X4's typed program image; refusing "
             "to dispatch address 0");
    std::abort();
  }
  cfg_logi("boot", "dispatching guest main() 0x%08X on the recompiled substrate", image->gameMainEntry);
  rec_dispatch(&core, image->gameMainEntry);
}

const GuestProgramImage *X4Runtime::guestProgramImage() const {
  return &legacy::measuredProgramImage;
}

bool X4Runtime::guestVramIsPicture(const Game &) const {
  // X4's shipping picture is the GTE primitive stream. Widescreen widens that stream's guest clip;
  // it does not turn persistent VRAM uploads into a second picture owner. No measured mode transition
  // currently changes that ownership, so the derived runtime answers false for every frame.
  return false;
}

const GuestWidescreenProjection *X4Runtime::guestWidescreenProjection() const {
  return &widescreenPolicy_;
}

} // namespace x4
