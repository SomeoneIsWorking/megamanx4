#include "movie_cleanup.h"

#include "bios_threads.h"
#include "cd_controller.h"
#include "cfg.h"
#include "core.h"
#include "execution_services.h"
#include "guest_execution.h"
#include "x4_context.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::movie_cleanup {
namespace {

constexpr std::uint32_t kResetMovieState = 0x800192F8u;
constexpr std::uint32_t kCdControlBlocking = 0x800E5FF4u;
constexpr std::uint32_t kCdDataCallback = 0x800E6178u;
constexpr std::uint32_t kCdReadyCallback = 0x800E5D78u;
constexpr std::uint32_t kDecDctOutCallback = 0x800ED084u;
constexpr std::uint32_t kStUnsetRing = 0x800E8130u;
constexpr std::uint32_t kCdControl = 0x800E5D90u;

constexpr std::uint32_t kPause = 9u;
constexpr std::uint32_t kSetMode = 14u;
constexpr std::uint32_t kDataMode = 0x80u;

[[noreturn]] void refuse(const char *reason) {
  lucent::error("x4-movie-cleanup", "movie cleanup transaction refused: {}", reason);
  std::abort();
}

void suspendRetailTask(Core &core) {
  bios_threads::from(core).yieldToMain();
}

void call(Core &core, GuestDispatch dispatch, std::uint32_t entry, std::uint32_t returnAddress, std::uint32_t ticks) {
  core.r[31] = returnAddress;
  psx::cpu::accountGuestInstructions(core, ticks);
  dispatch(&core, entry);
}

} // namespace

State::State(Core &core) : State(core, suspendRetailTask) {}

State::State(Core &core, SuspendField suspendField) : core_(core), suspendField_(suspendField) {
  if (!suspendField_) {
    refuse("host field suspension service is absent");
  }
}

void State::begin() {
  if (phase_ != Phase::Idle) {
    refuse("a second cleanup began while the first is active");
  }
  completedFields_ = 0u;
  phase_ = Phase::BeforeDisplayFence;
}

void State::yieldFields(std::uint32_t returnAddress, std::uint32_t fields) {
  Phase activePhase = Phase::Idle;
  Phase finishedPhase = Phase::Idle;
  std::uint32_t expectedFields = 0u;

  if (returnAddress == kDisplayFieldReturn && phase_ == Phase::BeforeDisplayFence) {
    activePhase = Phase::DisplayFence;
    finishedPhase = Phase::AfterDisplayFence;
    expectedFields = kDisplayFields;
  } else if (returnAddress == kResetFenceReturn && phase_ == Phase::AfterDisplayFence) {
    activePhase = Phase::ResetFence;
    finishedPhase = Phase::AfterResetFence;
    expectedFields = kSettlingFields;
  } else if (returnAddress == kSetModeFenceReturn && phase_ == Phase::AfterResetFence) {
    activePhase = Phase::SetModeFence;
    finishedPhase = Phase::AfterSetModeFence;
    expectedFields = kSettlingFields;
  } else {
    refuse("field fence order or return address differs from retained 0x80018E50");
  }

  if (core_.r[31] != returnAddress || core_.r[4] != fields || fields != expectedFields) {
    refuse("field fence ABI or count differs from retained 0x80018E50");
  }

  phase_ = activePhase;
  for (std::uint32_t field = 0u; field < fields; ++field) {
    suspendField_(core_);
    ++completedFields_;
  }
  core_.r[2] = 0u;
  phase_ = finishedPhase;
}

void State::complete() {
  if (phase_ != Phase::AfterSetModeFence || completedFields_ != kTotalFields) {
    refuse("cleanup returned before all seven retained fields completed");
  }
  phase_ = Phase::Idle;
}

bool State::pending() const {
  return phase_ != Phase::Idle;
}

Phase State::phase() const {
  return phase_;
}

std::uint32_t State::completedFields() const {
  return completedFields_;
}

void run(Core &core, State &state, GuestDispatch dispatch, ControllerReset resetController) {
  if (!dispatch || !resetController) {
    refuse("retained dispatcher or controller-reset owner is absent");
  }

  state.begin();

  // Exact activation and pre-fence sequence from SLUS_005.61 0x80018E50. Pause remains a normal
  // guest call through the 0x800E5FF4 original-call boundary; its title override routes command
  // 9 to the shared synchronous CD owner and never enters guest CdSync/VSync.
  core.r[29] -= 32u;
  core.r[2] = kDataMode;
  core.mem_w32(core.r[29] + 24u, core.r[31]);
  core.r[31] = 0x80018E64u;
  core.mem_w8(core.r[29] + 16u, static_cast<std::uint8_t>(core.r[2]));
  psx::cpu::accountGuestInstructions(core, 5u);
  dispatch(&core, kResetMovieState);

  core.r[4] = kPause;
  psx::cpu::accountGuestInstructions(core, 1u);
  do {
    core.r[5] = 0u;
    core.r[6] = 0u;
    call(core, dispatch, kCdControlBlocking, 0x80018E74u, 3u);
    core.r[4] = kPause;
    psx::cpu::accountGuestInstructions(core, 2u);
  } while (core.r[2] == 0u);

  core.r[4] = kDisplayFields;
  core.r[31] = kDisplayFieldReturn;
  psx::cpu::accountGuestInstructions(core, 2u);
  state.yieldFields(core.r[31], core.r[4]);

  core.r[4] = 0u;
  call(core, dispatch, kCdDataCallback, 0x80018E8Cu, 2u);
  core.r[4] = 0u;
  call(core, dispatch, kCdReadyCallback, 0x80018E94u, 2u);
  core.r[4] = 0u;
  call(core, dispatch, kDecDctOutCallback, 0x80018E9Cu, 2u);
  call(core, dispatch, kStUnsetRing, 0x80018EA4u, 2u);

  // CdReset(0) is a synchronous native controller transaction. Clear the exact stock libcd command
  // state and publish a ready controller once; there is no guest polling loop or borrowed clock.
  core.r[4] = 0u;
  core.r[31] = 0x80018EACu;
  psx::cpu::accountGuestInstructions(core, 2u);
  cd_controller::clearCommandState(core);
  resetController(core);
  core.r[2] = 1u;
  psx::cpu::accountGuestInstructions(core, 2u);

  core.r[4] = kSettlingFields;
  core.r[31] = kResetFenceReturn;
  psx::cpu::accountGuestInstructions(core, 2u);
  state.yieldFields(core.r[31], core.r[4]);

  core.r[4] = kSetMode;
  psx::cpu::accountGuestInstructions(core, 1u);
  do {
    core.r[5] = core.r[29] + 16u;
    core.r[6] = 0u;
    call(core, dispatch, kCdControl, 0x80018ECCu, 3u);
    core.r[4] = kSetMode;
    psx::cpu::accountGuestInstructions(core, 2u);
  } while (core.r[2] == 0u);

  core.r[4] = kSettlingFields;
  core.r[31] = kSetModeFenceReturn;
  psx::cpu::accountGuestInstructions(core, 2u);
  state.yieldFields(core.r[31], core.r[4]);

  core.r[31] = core.mem_r32(core.r[29] + 24u);
  core.r[29] += 32u;
  psx::cpu::accountGuestInstructions(core, 4u);
  state.complete();
}

void run(Core *core) {
  if (!core) {
    refuse("Core is null");
  }
  run(*core, context(*core).movieCleanup, guest::call, cd_controller::reset);
}

void registerOverride(Core &core) {
  guest::install(core, kEntry, "movie_cleanup::run", static_cast<void (*)(Core *)>(run));
}

} // namespace x4::movie_cleanup
