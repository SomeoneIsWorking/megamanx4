#include "x4_runtime.h"

#include "bios_threads.h"
#include "cfg.h"
#include "core.h"
#include "cull_overrides.h"
#include "display_init.h"
#include "game.h"
#include "gpu_timeout.h"
#include "guest_execution.h"

#include "legacy_game_interface.h"
#include "movie_cleanup.h"
#include "music_stream.h"
#include "native_overrides.h"
#include "pad_layout.h"
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
  // No legacy adapter vtable is linked, so its Fps60 factory cannot drag interpolation into this
  // 60 Hz title.
  bindLegacyInterface(&legacy::measuredConfig(), &legacy::compatibilityHooks());
}

void *X4Runtime::createContext(Core &core) {
  return new X4Context(core);
}

void X4Runtime::destroyContext(void *context) {
  delete static_cast<X4Context *>(context);
}

void X4Runtime::registerOverrides(Game &game) {
  bios_threads::install(game);
  display_init::registerOverride(game.core);
  gpu_timeout::registerOverride(game.core);
  vsync::registerOverrides(game.core);
  movie_cleanup::registerOverride(game.core);
  music_stream::registerOverride(game.core);
  startup_cd::registerOverride(game.core);
  stream_interrupt::registerOverride(game.core);
  stream_startup::registerOverride(game.core);
  title_quad::registerOverride(game.core);
  // The recovered predicate in visibility_cull.cpp is bound to the seam by cull_overrides.cpp.
  cull::registerOverrides(game.core);
  // Loading-coroutine owners are registered by authenticated image/address and keep scoped Lightrec
  // original calls where required.
  native_overrides::install(game.core);
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

std::unique_ptr<FrameDriver> X4Runtime::createFrameDriver(Game &game) {
  return std::make_unique<frame::X4FrameDriver>(guest::callWithoutKnownReturn,
                                                vsync::deliverField,
                                                synchronizePresentation,
                                                context(game.core).movieCleanup,
                                                context(game.core).musicStream,
                                                context(game.core).biosThreads);
}

const GuestPadBufferLayout *X4Runtime::guestPadBufferLayout() const {
  return &pad::kGuestBufferLayout;
}

const GuestProgramImage *X4Runtime::guestProgramImage() const {
  return &legacy::measuredProgramImage();
}

// The device VRAM is the picture on the record path, STR frames included.
bool X4Runtime::guestVramIsPicture(const Game &) const {
  return true;
}

const GuestWidescreenProjection *X4Runtime::guestWidescreenProjection() const {
  return &widescreenPolicy_;
}

} // namespace x4
