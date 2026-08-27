#include "core.h"
#include "game.h"
#include "x4_frame_driver.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>

namespace {

struct Call {
  std::uint32_t entry;
  std::uint32_t returnAddress;
  std::uint32_t a0;
  std::uint32_t a1;
};

std::vector<Call> g_calls;
std::uint32_t g_fieldServices = 0;
std::uint32_t g_presentationSyncs = 0;
bool g_releaseMovieOnUpdate = false;

void recordDispatch(Core *core, std::uint32_t entry) {
  g_calls.push_back({entry, core->r[31], core->r[4], core->r[5]});
  if (g_releaseMovieOnUpdate && entry == 0x80012600u) {
    core->game->cd.stream_active = 0;
  }
}

void recordField(Core &) {
  ++g_fieldServices;
}

void recordPresentationSync(Core &) {
  ++g_presentationSyncs;
}

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_frame_driver: %s\n", message);
  }
  return condition;
}

bool verifyBootPrefix(Core &core) {
  constexpr std::uint32_t kInitialStack = 0x801FFF00u;
  constexpr std::uint32_t kInitialRa = 0x81234567u;
  constexpr std::uint32_t kInitialS0 = 0x10203040u;
  constexpr std::uint32_t kInitialS1 = 0x50607080u;
  core.r[29] = kInitialStack;
  core.r[31] = kInitialRa;
  core.r[16] = kInitialS0;
  core.r[17] = kInitialS1;
  g_calls.clear();

  x4::frame::bootPrefix(core, recordDispatch);

  return check(g_calls.size() == 2u, "boot prefix did not dispatch exactly two retail leaves") &&
         check(g_calls[0].entry == 0x800DAE84u && g_calls[0].returnAddress == 0x80012038u,
               "boot prefix changed the first retail call edge") &&
         check(g_calls[1].entry == 0x8001213Cu && g_calls[1].returnAddress == 0x80012040u,
               "boot prefix changed the initialization call edge") &&
         check(core.r[29] == kInitialStack - 32u, "boot prefix did not preserve the retail main stack frame") &&
         check(core.mem_r32(core.r[29] + 24u) == kInitialRa && core.mem_r32(core.r[29] + 20u) == kInitialS1 &&
                   core.mem_r32(core.r[29] + 16u) == kInitialS0,
               "boot prefix saved the wrong main registers") &&
         check(core.r[17] == 0x1F800000u && core.r[16] == 0x80141BD8u,
               "boot prefix did not publish the retail loop bases");
}

bool verifyFrameStep(Core &core) {
  constexpr std::uint32_t kDrawInfo0 = 0x80166C10u;
  constexpr std::uint32_t kDrawInfo1 = kDrawInfo0 + 160u;
  constexpr std::uint32_t kCurrentDrawInfo = 0x80142F80u;
  constexpr std::uint32_t kDrawInfoPosition = 0x1F800000u;
  constexpr std::uint32_t kFieldCounter = 0x80141BD8u;
  constexpr std::array<std::uint32_t, 15> kEntries = {
      0x800EAAD8u,
      0x800EA880u,
      0x800EA80Cu,
      0x800EA714u,
      0x800168D8u,
      0x800169D8u,
      0x80012328u,
      0x80015E0Cu,
      0x80012600u,
      0x80014780u,
      0x800EA20Cu,
      0x80015E54u,
      0x80016004u,
      0x800EA20Cu,
      0x80012454u,
  };

  core.mem_w32(kDrawInfoPosition, 0u);
  core.mem_w32(kCurrentDrawInfo, kDrawInfo0);
  core.mem_w32(kFieldCounter, 41u);
  g_calls.clear();
  g_fieldServices = 0;
  g_presentationSyncs = 0;

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync);
  driver.stepFrame(core, 7u);

  if (!check(g_presentationSyncs == 1u, "one frame did not synchronize title presentation exactly once") ||
      !check(g_fieldServices == 1u, "one frame did not service exactly one display field") ||
      !check(g_calls.size() == kEntries.size(), "one frame dispatched the wrong number of retail leaves")) {
    return false;
  }
  for (std::size_t i = 0; i < kEntries.size(); ++i) {
    if (!check(g_calls[i].entry == kEntries[i], "retail frame call order changed")) {
      return false;
    }
  }
  return check(g_calls[0].a0 == kDrawInfo0, "PutDispEnv received the wrong display environment") &&
         check(g_calls[1].a0 == kDrawInfo0 + 20u, "PutDrawEnv received the wrong draw environment") &&
         check(g_calls[2].a0 == kDrawInfo0 + 156u, "DrawOTag received the wrong ordering table") &&
         check(g_calls[3].a0 == kDrawInfo1 + 112u && g_calls[3].a1 == 12u,
               "ClearOTagR received the wrong next-buffer table") &&
         check(g_calls[10].a0 == 0u && g_calls[13].a0 == 0u, "DrawSync mode changed") &&
         check(core.mem_r32(kDrawInfoPosition) == 1u && core.mem_r32(kCurrentDrawInfo) == kDrawInfo1,
               "frame step did not flip the retail draw buffer") &&
         check(core.mem_r32(kFieldCounter) == 42u, "frame step did not increment the retail frame counter once");
}

bool verifyMovieOwnedFrame(Core &core) {
  constexpr std::uint32_t kCurrentDrawInfo = 0x80142F80u;
  constexpr std::uint32_t kDrawInfoPosition = 0x1F800000u;
  constexpr std::uint32_t kFieldCounter = 0x80141BD8u;
  core.mem_w32(kDrawInfoPosition, 1u);
  core.mem_w32(kCurrentDrawInfo, 0x80166CB0u);
  core.mem_w32(kFieldCounter, 91u);
  core.game->cd.stream_active = 1;
  g_calls.clear();
  g_fieldServices = 0;
  g_presentationSyncs = 0;
  g_releaseMovieOnUpdate = false;

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync);
  driver.stepFrame(core, 8u);

  return check(g_fieldServices == 1u && g_presentationSyncs == 1u,
               "movie-owned frame did not retain the one native field boundary") &&
         check(g_calls.size() == 1u && g_calls[0].entry == 0x80012600u,
               "movie-owned frame ran unrelated gameplay drawing or frame-tail work") &&
         check(core.mem_r32(kDrawInfoPosition) == 1u && core.mem_r32(kCurrentDrawInfo) == 0x80166CB0u,
               "movie-owned frame changed the gameplay draw buffer") &&
         check(core.mem_r32(kFieldCounter) == 91u, "movie-owned frame advanced the blocked outer main-loop counter");
}

bool verifyMovieReleaseResumesFrameTail(Core &core) {
  constexpr std::array<std::uint32_t, 7> kEntries = {
      0x80012600u,
      0x80014780u,
      0x800EA20Cu,
      0x80015E54u,
      0x80016004u,
      0x800EA20Cu,
      0x80012454u,
  };
  core.game->cd.stream_active = 1;
  g_calls.clear();
  g_releaseMovieOnUpdate = true;

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync);
  driver.stepFrame(core, 9u);
  g_releaseMovieOnUpdate = false;

  if (!check(g_calls.size() == kEntries.size(), "movie release did not resume the blocked frame tail")) {
    return false;
  }
  for (std::size_t i = 0; i < kEntries.size(); ++i) {
    if (!check(g_calls[i].entry == kEntries[i], "movie release resumed at the wrong retail call edge")) {
      return false;
    }
  }
  return true;
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  if (!verifyBootPrefix(game->core) || !verifyFrameStep(game->core) || !verifyMovieOwnedFrame(game->core) ||
      !verifyMovieReleaseResumesFrameTail(game->core)) {
    return 1;
  }
  std::puts("x4_frame_driver: normal and movie-owned finite frame transactions passed");
  return 0;
}
