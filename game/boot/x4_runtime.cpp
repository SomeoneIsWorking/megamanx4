#include "x4_runtime.h"

#include "background_overrides.h"
#include "bios_threads.h"
#include "crt0_boot.h"
#include "cull_overrides.h"
#include "display_init.h"
#include "enhancements.h"
#include "gpu_timeout.h"
#include "guest_execution.h"
#include "hud_overrides.h"
#include "movie_cleanup.h"
#include "music_stream.h"
#include "native_overrides.h"
#include "pad_layout.h"
#include "sequence_skip_overrides.h"
#include "startup_cd.h"
#include "stream_interrupt.h"
#include "stream_startup.h"
#include "title_quad.h"
#include "vram_rect_queue.h"
#include "vsync_sync.h"
#include "x4_frame_driver.h"
#include "x4_session.h"

#include "core.h"
#include "game.h"

#include <cstdio>
#include <lucent/log.h>
#include <memory>
#include <string>
#include <string_view>

namespace x4 {
namespace {

// crt0 at the PS-EXE entry 0x800DAE8C of SLUS_005.61. It has no stack-top bias and keeps the heap
// size and base in registers only.
constexpr psx::game::Crt0Image kCrt0{
    .bss = {0x8012F418u, 0x80175F38u},
    .stackTopWordAddress = 0x800DAF3Cu,
    .stackReserveWordAddress = 0x8011CB74u,
    .heapBase = 0x80175F38u,
    .heapSizeStoreAddress = 0,
    .heapBaseStoreAddress = 0,
    .globalPointer = 0x8012F418u,
    .libcInitEntry = 0x800EDCDCu, // BIOS A(39h) InitHeap thunk
    .crt0Entry = 0x800DAE8Cu,
    .stackBias = {.declared = true, .bytes = 0},
};

constexpr psx::game::HostIdentity kHostIdentity{
    .cardEnvVar = "PSXPORT_X4_CARD",
    .cardDefaultPath = "scratch/saves/megamanx4.mcr",
    .userDataName = "megamanx4",
};

void synchronizePresentation(Core &core) {
  session(core).widescreen.synchronizePresentation(core);
}

} // namespace

// The retail libcd stays guest code; its object only lends its bodies to the title's CD wrappers.
X4Runtime::X4Runtime()
    : vsync_(vsync::kVSync, vsync::kVblankCounter), dmaCallbacks_(stream_startup::kDmaCallbackTable), libcd_({}, {}, 0),
      pad_({.slot0Buffer = pad::kSlot0Buffer, .slot1Buffer = pad::kSlot1Buffer}) {}

void X4Runtime::startProgram(Core &core) {
  psx::game::Crt0Boot{kCrt0}.run(core);
  lucent::info("boot", "executing the finite prefix of gameMain 0x80012024; X4FrameDriver owns repetition");
  frame::bootPrefix(core);
}

void X4Runtime::registerOverrides(Game &game) {
  reportUnreadEnhancements();
  // vsync::serveVSync overrides the entry and answers VSync(<0) through this binding's counter.
  vsync_.bind(game);
  dmaCallbacks_.bind(game);
  libcd_.bind(game);
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
  cull::registerOverrides(game.core);
  background::registerOverrides(game.core);
  hud::registerOverrides(game.core);
  sequence_skip::registerOverrides(game.core);
  native_overrides::install(game.core);
}

std::unique_ptr<psx::game::TitleSessionState> X4Runtime::createSession(Game &game) {
  return std::make_unique<X4Session>(game.core, libcd_);
}

std::unique_ptr<psx::game::FrameDriver> X4Runtime::createFrameDriver(Game &game) {
  X4Session &state = session(game.core);
  return std::make_unique<frame::X4FrameDriver>(
      guest::callWithoutKnownReturn,
      frame::FieldServices{.deliverField = vsync::deliverField, .synchronizePresentation = synchronizePresentation},
      state.movieCleanup,
      state.musicStream,
      state.biosThreads,
      state.stageWarp);
}

void X4Runtime::deliverPad(Core &core, const psx::input::PadDelivery &delivery) {
  pad_.deliver(core, delivery);
}

// The device's GP0 work replayed from the frame record; no native producers.
RenderCapabilities X4Runtime::renderCapabilities() const {
  return RenderCapabilities{
      .defaultPath = RenderPath::Record,
      .nativeRenderPath = false,
  };
}

// The device VRAM is the picture on the record path, STR frames included.
bool X4Runtime::guestVramIsPicture(const Game &) const {
  return true;
}

const GuestWidescreenProjection *X4Runtime::guestWidescreenProjection() const {
  return &widescreenPolicy_;
}

bool X4Runtime::titleCommand(Core &core, const psx::game::TitleCommandLine &input, std::FILE *reply) {
  if (std::string_view(input.command) != "warp") {
    return false;
  }
  const std::string answer = session(core).stageWarp.arm(input.line);
  std::fprintf(reply, "%s\n", answer.c_str());
  return true;
}

psx::game::TitleDevWarp *X4Runtime::devWarp(Core &core) const {
  return &session(core).stageWarp;
}

void X4Runtime::reportRun(Core &core) const {
  vram_rect::reportCensus("run end");
  bios_threads::from(core).reportCensus("run end");
}

const psx::game::HostIdentity *X4Runtime::hostIdentity() const {
  return &kHostIdentity;
}

} // namespace x4
