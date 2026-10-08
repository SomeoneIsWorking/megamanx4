#include "core.h"
#include "coro.h"
#include "game.h"
#include "movie_cleanup.h"
#include "music_stream.h"
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
x4::music_stream::State *g_musicStream = nullptr;
bool g_yieldMusicFields = false;
bool g_runMovieCleanup = false;
x4::movie_cleanup::State *g_movieCleanup = nullptr;
std::unique_ptr<Coro> g_cleanupTransaction;

void cleanupDispatch(Core *core, std::uint32_t entry) {
  if (entry == 0x800E5FF4u) {
    core->game->cd.stream_active = 0;
  }
  core->r[2] = 1u;
}

void cleanupReset(Core &core) {
  core.game->cd.stream_active = 0;
}

void suspendCleanupField(Core &) {
  g_cleanupTransaction->yield();
}

void recordDispatch(Core *core, std::uint32_t entry) {
  g_calls.push_back({entry, core->r[31], core->r[4], core->r[5]});
  if (g_yieldMusicFields && entry == x4::music_stream::kBeforeObjectsB) {
    core->r[31] = x4::music_stream::kSetModeFieldReturn;
    core->r[4] = x4::music_stream::kSetModeFields;
    g_musicStream->yieldFields(core->r[31], core->r[4]);
  }
  if (g_releaseMovieOnUpdate && entry == 0x80012600u) {
    core->game->cd.stream_active = 0;
  }
  if (g_runMovieCleanup && entry == 0x80012600u) {
    if (!g_cleanupTransaction) {
      g_cleanupTransaction = std::make_unique<Coro>();
      g_cleanupTransaction->start([core] {
        x4::movie_cleanup::run(*core, *g_movieCleanup, cleanupDispatch, cleanupReset);
      });
    }
    g_cleanupTransaction->resume();
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

bool verifyFrameStep(Core &core, x4::movie_cleanup::State &movieCleanup, x4::music_stream::State &musicStream) {
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

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync, movieCleanup, musicStream);
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

bool verifyMovieOwnedFrame(Core &core, x4::movie_cleanup::State &movieCleanup, x4::music_stream::State &musicStream) {
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

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync, movieCleanup, musicStream);
  driver.stepFrame(core, 8u);

  return check(g_fieldServices == 1u && g_presentationSyncs == 1u,
               "movie-owned frame did not retain the one native field boundary") &&
         check(g_calls.size() == 1u && g_calls[0].entry == 0x80012600u,
               "movie-owned frame ran unrelated gameplay drawing or frame-tail work") &&
         check(core.mem_r32(kDrawInfoPosition) == 1u && core.mem_r32(kCurrentDrawInfo) == 0x80166CB0u,
               "movie-owned frame changed the gameplay draw buffer") &&
         check(core.mem_r32(kFieldCounter) == 91u, "movie-owned frame advanced the blocked outer main-loop counter");
}

bool verifyMovieReleaseResumesFrameTail(Core &core,
                                        x4::movie_cleanup::State &movieCleanup,
                                        x4::music_stream::State &musicStream) {
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

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync, movieCleanup, musicStream);
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

bool verifyMusicFieldTransaction(Core &core,
                                 x4::movie_cleanup::State &movieCleanup,
                                 x4::music_stream::State &musicStream) {
  constexpr std::uint32_t kDrawInfo0 = 0x80166C10u;
  constexpr std::uint32_t kCurrentDrawInfo = 0x80142F80u;
  constexpr std::uint32_t kDrawInfoPosition = 0x1F800000u;
  constexpr std::uint32_t kFieldCounter = 0x80141BD8u;

  core.game->cd.stream_active = 0;
  core.mem_w32(kDrawInfoPosition, 0u);
  core.mem_w32(kCurrentDrawInfo, kDrawInfo0);
  core.mem_w32(kFieldCounter, 23u);
  core.mem_w32(x4::music_stream::kMusicActive, 2u);
  core.mem_w32(x4::music_stream::kMachineState, 7u);
  g_calls.clear();
  g_fieldServices = 0;
  g_presentationSyncs = 0;
  g_musicStream = &musicStream;
  g_yieldMusicFields = true;

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync, movieCleanup, musicStream);
  driver.stepFrame(core, 10u);
  if (!check(musicStream.pending(), "music VSync(3) replacement did not suspend its retail call chain") ||
      !check(g_calls.size() == 6u && g_calls.back().entry == x4::music_stream::kBeforeObjectsB,
             "music field fence did not stop exactly inside BeforeObjectsB") ||
      !check(core.mem_r32(kFieldCounter) == 23u, "music field fence advanced the blocked outer frame")) {
    return false;
  }

  driver.stepFrame(core, 11u);
  driver.stepFrame(core, 12u);
  if (!check(musicStream.pending(), "music field fence resumed before three host-owned fields") ||
      !check(g_calls.size() == 6u, "music field fence replayed the retail frame prefix")) {
    return false;
  }

  driver.stepFrame(core, 13u);
  g_yieldMusicFields = false;
  g_musicStream = nullptr;
  core.mem_w32(x4::music_stream::kMusicActive, 0u);
  core.mem_w32(x4::music_stream::kMachineState, 0u);

  return check(!musicStream.pending(), "music field fence did not finish on the third host field") &&
         check(g_fieldServices == 4u && g_presentationSyncs == 4u,
               "music field fence did not consume exactly three additional native fields") &&
         check(g_calls.size() == 15u, "music field fence did not resume the blocked frame tail") &&
         check(core.mem_r32(kFieldCounter) == 24u, "music field fence did not finish the outer frame exactly once");
}

bool verifyCleanupFieldTransaction(Core &core,
                                   x4::movie_cleanup::State &movieCleanup,
                                   x4::music_stream::State &musicStream) {
  core.game->cd.stream_active = 1;
  g_calls.clear();
  g_fieldServices = 0u;
  g_presentationSyncs = 0u;
  g_runMovieCleanup = true;
  g_movieCleanup = &movieCleanup;
  g_cleanupTransaction.reset();

  x4::frame::X4FrameDriver driver(recordDispatch, recordField, recordPresentationSync, movieCleanup, musicStream);
  driver.stepFrame(core, 20u);
  if (!check(movieCleanup.pending() && movieCleanup.phase() == x4::movie_cleanup::Phase::DisplayFence,
             "movie cleanup did not suspend at its first display field") ||
      !check(core.game->cd.stream_active == 0, "Pause did not release the stream before cleanup suspension") ||
      !check(g_calls.size() == 1u && g_calls[0].entry == 0x80012600u,
             "cleanup entry ran gameplay work around blocked UpdateTasks")) {
    return false;
  }

  constexpr std::array<x4::movie_cleanup::Phase, x4::movie_cleanup::kTotalFields - 1u> kPendingPhases = {
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::ResetFence,
      x4::movie_cleanup::Phase::SetModeFence,
      x4::movie_cleanup::Phase::SetModeFence,
      x4::movie_cleanup::Phase::SetModeFence,
  };
  for (std::size_t field = 0u; field < kPendingPhases.size(); ++field) {
    driver.stepFrame(core, 21u + static_cast<std::uint32_t>(field));
    if (!check(movieCleanup.pending() && movieCleanup.phase() == kPendingPhases[field],
               "cleanup resumed at the wrong retained field phase") ||
        !check(g_calls.size() == field + 2u, "cleanup replayed outer drawing while its stack was blocked")) {
      return false;
    }
  }

  driver.stepFrame(core, 27u);
  g_runMovieCleanup = false;
  g_movieCleanup = nullptr;

  if (!check(g_cleanupTransaction && g_cleanupTransaction->done(),
             "cleanup retained stack did not return after its seventh field") ||
      !check(!movieCleanup.pending() && movieCleanup.completedFields() == x4::movie_cleanup::kTotalFields,
             "cleanup FSM did not complete all seven host-owned fields") ||
      !check(g_fieldServices == 8u && g_presentationSyncs == 8u,
             "cleanup did not consume exactly seven additional native fields")) {
    return false;
  }

  constexpr std::array<std::uint32_t, 6> kTail = {
      0x80014780u,
      0x800EA20Cu,
      0x80015E54u,
      0x80016004u,
      0x800EA20Cu,
      0x80012454u,
  };
  if (!check(g_calls.size() == 8u + kTail.size(), "cleanup did not resume the outer frame tail exactly once")) {
    return false;
  }
  for (std::size_t field = 0u; field < 8u; ++field) {
    if (!check(g_calls[field].entry == 0x80012600u, "cleanup resumed through a non-UpdateTasks entry")) {
      return false;
    }
  }
  for (std::size_t call = 0u; call < kTail.size(); ++call) {
    if (!check(g_calls[8u + call].entry == kTail[call], "cleanup resumed the wrong outer frame-tail edge")) {
      return false;
    }
  }
  return true;
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  x4::movie_cleanup::State movieCleanup(game->core, suspendCleanupField);
  x4::music_stream::State musicStream(game->core);
  if (!verifyBootPrefix(game->core) || !verifyFrameStep(game->core, movieCleanup, musicStream) ||
      !verifyMovieOwnedFrame(game->core, movieCleanup, musicStream) ||
      !verifyMovieReleaseResumesFrameTail(game->core, movieCleanup, musicStream) ||
      !verifyMusicFieldTransaction(game->core, movieCleanup, musicStream) ||
      !verifyCleanupFieldTransaction(game->core, movieCleanup, musicStream)) {
    return 1;
  }
  std::puts("x4_frame_driver: normal, movie, cleanup, and XA/BGM finite field transactions passed");
  return 0;
}
