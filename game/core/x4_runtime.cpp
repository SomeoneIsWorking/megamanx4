#include "x4_runtime.h"

#include "bios_threads.h"
#include "cfg.h"
#include "core.h"
#include "display_init.h"
#include "game.h"
#include "gpu_timeout.h"
#include "legacy_game_interface.h"
#include "movie_field.h"
#include "pad_layout.h"
#include "recomp_register.h"
#include "startup_cd.h"
#include "stream_interrupt.h"
#include "stream_startup.h"
#include "title_quad.h"
#include "vsync_sync.h"
#include "x4_context.h"
#include "x4_frame_driver.h"

#include <cstdlib>
#include <memory>

namespace x4 {
namespace {

void synchronizePresentation(Core &core) {
  context(core).widescreen.synchronizePresentation(core);
}

} // namespace

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
  bios_threads::install(game);
  display_init::registerOverride();
  gpu_timeout::registerOverride();
  movie::registerOverrides();
  startup_cd::registerOverride();
  stream_interrupt::registerOverride();
  stream_startup::registerOverride();
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
  cfg_logi("boot",
           "executing finite prefix of guest main() 0x%08X; native frame shell owns repetition",
           image->gameMainEntry);
  frame::bootPrefix(core);
}

std::unique_ptr<FrameDriver> X4Runtime::createFrameDriver(Game &) {
  return std::make_unique<frame::X4FrameDriver>(rec_dispatch, vsync::deliverField, synchronizePresentation);
}

const GuestPadBufferLayout *X4Runtime::guestPadBufferLayout() const {
  return &pad::kGuestBufferLayout;
}

const GuestProgramImage *X4Runtime::guestProgramImage() const {
  return &legacy::measuredProgramImage;
}

bool X4Runtime::guestVramIsPicture(const Game &game) const {
  // Ordinary X4 gameplay is the GTE primitive stream, but the title's STR path is the measured
  // ownership transition: while its continuous CD stream is active, MDEC output reaches the display
  // exclusively through 24-bit LoadImage slices in guest VRAM. The native CD controller clears this
  // bit on the guest's Pause/Stop command, returning ownership to the primitive stream without a
  // frame-type heuristic or a renderer-specific special case.
  return game.cd.stream_active != 0;
}

const GuestWidescreenProjection *X4Runtime::guestWidescreenProjection() const {
  return &widescreenPolicy_;
}

} // namespace x4
