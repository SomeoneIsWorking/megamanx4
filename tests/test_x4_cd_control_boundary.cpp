#include "cd_control_boundary.h"

#include "cd_control.h"
#include "core.h"
#include "game.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

std::uint32_t gRetailCalls = 0u;
std::uint32_t gExistingPolicyCalls = 0u;
std::uint32_t gSynchronousCalls = 0u;
std::uint32_t gSetModeCalls = 0u;
std::uint8_t gSetMode = 0u;
bool gExistingBlocking = false;

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_cd_control_boundary: %s\n", message);
  }
  return condition;
}

void retainedSuper(Core *core) {
  ++gRetailCalls;
  core->r[2] = 0xC0DEC0DEu;
}

void synchronousPause(Core *core) {
  ++gSynchronousCalls;
  cd_control_sync(core);
}

void existingPolicy(Core *core, x4::cd_control_boundary::GuestBody retailBody, bool blocking) {
  ++gExistingPolicyCalls;
  gExistingBlocking = blocking;
  retailBody(core);
}

void synchronousSetMode(Core &, std::uint8_t mode) {
  ++gSetModeCalls;
  gSetMode = mode;
}

bool verifyPause(Core &core, Game &game) {
  constexpr std::uint32_t kResult = 0x80110080u;
  gRetailCalls = 0u;
  gExistingPolicyCalls = 0u;
  gSynchronousCalls = 0u;
  gExistingBlocking = false;

  game.xa.active = 1;
  game.cd.stock_reading = 1;
  game.cd.stream_active = 1;
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    core.mem_w8(kResult + byte, 0xFFu);
  }
  core.r[4] = x4::cd_control_boundary::kPauseCommand;
  core.r[5] = 0u;
  core.r[6] = kResult;

  x4::cd_control_boundary::blocking(&core, retainedSuper, synchronousPause, existingPolicy);

  if (!check(gSynchronousCalls == 1u, "Pause did not use the synchronous CD owner") ||
      !check(gRetailCalls == 0u && gExistingPolicyCalls == 0u,
             "Pause entered the retained guest/VSync or loading policy") ||
      !check(core.r[2] == 1u, "Pause did not preserve CdControlB success") ||
      !check(game.xa.active == 0 && game.cd.stock_reading == 0 && game.cd.stream_active == 0,
             "Pause did not release XA, finite-read, and continuous-stream ownership")) {
    return false;
  }
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    if (!check(core.mem_r8(kResult + byte) == 0u, "Pause did not publish the eight-byte result contract")) {
      return false;
    }
  }
  return true;
}

bool verifyNonPausePreservation(Core &core) {
  gRetailCalls = 0u;
  gExistingPolicyCalls = 0u;
  gSynchronousCalls = 0u;
  gExistingBlocking = false;
  core.r[4] = 0x01u;

  x4::cd_control_boundary::blocking(&core, retainedSuper, synchronousPause, existingPolicy);

  return check(gSynchronousCalls == 0u, "non-Pause command used the Pause owner") &&
         check(gExistingPolicyCalls == 1u && gExistingBlocking,
               "non-Pause command did not retain the existing blocking policy") &&
         check(gRetailCalls == 1u && core.r[2] == 0xC0DEC0DEu,
               "non-Pause command did not preserve the retained super path");
}

bool verifyCleanupSetMode(Core &core) {
  constexpr std::uint32_t kParameter = 0x80110090u;
  gRetailCalls = 0u;
  gExistingPolicyCalls = 0u;
  gSetModeCalls = 0u;
  gSetMode = 0u;
  gExistingBlocking = true;
  core.mem_w8(kParameter, 0x80u);
  core.r[4] = x4::cd_control_boundary::kSetModeCommand;
  core.r[5] = kParameter;
  core.r[6] = 0u;
  core.r[31] = x4::cd_control_boundary::kCleanupSetModeReturn;

  x4::cd_control_boundary::control(&core, retainedSuper, existingPolicy, synchronousSetMode);

  return check(gSetModeCalls == 1u && gSetMode == 0x80u,
               "cleanup Setmode did not reach the synchronous controller owner") &&
         check(gExistingPolicyCalls == 0u && gRetailCalls == 0u,
               "cleanup Setmode entered the retained guest CdSync/VSync path") &&
         check(core.r[2] == 1u, "cleanup Setmode did not preserve CdControl success");
}

bool verifyMusicSetMode(Core &core) {
  constexpr std::uint32_t kParameter = 0x80110090u;
  gRetailCalls = 0u;
  gExistingPolicyCalls = 0u;
  gSetModeCalls = 0u;
  gSetMode = 0u;
  core.mem_w8(kParameter, 0xC8u);
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    core.mem_w8(x4::cd_control_boundary::kMusicSetModeResult + byte, 0xFFu);
  }
  core.r[4] = x4::cd_control_boundary::kSetModeCommand;
  core.r[5] = kParameter;
  core.r[6] = x4::cd_control_boundary::kMusicSetModeResult;
  core.r[31] = x4::cd_control_boundary::kMusicSetModeReturn;

  x4::cd_control_boundary::control(&core, retainedSuper, existingPolicy, synchronousSetMode);

  if (!check(gSetModeCalls == 1u && gSetMode == 0xC8u,
             "music Setmode did not reach the synchronous controller owner") ||
      !check(gExistingPolicyCalls == 0u && gRetailCalls == 0u,
             "music Setmode entered the retained guest CdSync/VSync path") ||
      !check(core.r[2] == 1u, "music Setmode did not preserve CdControl success")) {
    return false;
  }
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    if (!check(core.mem_r8(x4::cd_control_boundary::kMusicSetModeResult + byte) == 0u,
               "music Setmode did not publish the eight-byte result contract")) {
      return false;
    }
  }
  return true;
}

bool verifyOtherSetModePreservation(Core &core) {
  constexpr std::uint32_t kParameter = 0x80110090u;
  gRetailCalls = 0u;
  gExistingPolicyCalls = 0u;
  gSetModeCalls = 0u;
  gExistingBlocking = true;
  core.mem_w8(kParameter, 0xC8u);
  core.r[4] = x4::cd_control_boundary::kSetModeCommand;
  core.r[5] = kParameter;
  core.r[6] = 0u;
  core.r[31] = 0x81234567u;

  x4::cd_control_boundary::control(&core, retainedSuper, existingPolicy, synchronousSetMode);

  return check(gSetModeCalls == 0u, "unrelated Setmode borrowed the cleanup owner") &&
         check(gExistingPolicyCalls == 1u && !gExistingBlocking,
               "unrelated Setmode did not retain the nonblocking policy") &&
         check(gRetailCalls == 1u && core.r[2] == 0xC0DEC0DEu,
               "unrelated Setmode did not preserve the retained super path");
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  if (!verifyPause(game->core, *game) || !verifyNonPausePreservation(game->core) || !verifyCleanupSetMode(game->core) ||
      !verifyMusicSetMode(game->core) || !verifyOtherSetModePreservation(game->core)) {
    return 1;
  }
  std::puts("x4_cd_control_boundary: Pause, cleanup/music Setmode, and retained other-command contracts passed");
  return 0;
}
