#include "music_stream.h"

#include "cd_control.h"
#include "cfg.h"
#include "core.h"
#include "coro.h"
#include "execution_services.h"
#include "guest_execution.h"
#include "x4_context.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::music_stream {
namespace {

constexpr std::uint32_t kResult = 0x80139554u;
constexpr std::uint32_t kError = 0x8013952Cu;
constexpr std::uint32_t kComplete = 2u;
constexpr std::uint32_t kSetMode = 0x0Eu;
constexpr std::uint32_t kXaMode = 0xC8u;
constexpr std::uint32_t kNextState = 6u;
constexpr std::uint32_t kStatusError = 0x10u;

[[noreturn]] void refuse(const char *reason) {
  lucent::error("x4-music", "XA/BGM field transaction refused: {}", reason);
  std::abort();
}

void require(Core *core, GuestBody body, const char *name) {
  if (!core) {
    refuse("Core is null");
  }
  if (!body) {
    lucent::error("x4-music", "XA/BGM state 7 is missing retained {} body", name);
    std::abort();
  }
}

void yieldSetModeFields(Core &core, std::uint32_t returnAddress, std::uint32_t fields) {
  x4::context(core).musicStream.yieldFields(returnAddress, fields);
}

void cdControl(Core *core) {
  guest::call(core, 0x800E5D90u);
}

void runSetMode(Core *core) {
  // Retail reaches CdSync(1, nullptr) at 0x80016E9C before issuing the state-7 Setmode command.
  // The disc controller is already synchronous under the native frame loop, so use its stock-Sony
  // completion owner directly. Entering the retained wrapper would poll through guest VSync(-1).
  setMode(core, cd_sync_stock_sync, cdControl, yieldSetModeFields);
}

} // namespace

void setMode(Core *core, GuestBody cdSync, GuestBody cdControl, FieldYield yieldFields) {
  require(core, cdSync, "CdSync");
  require(core, cdControl, "CdControl");
  if (!yieldFields) {
    refuse("host field-yield owner is absent");
  }

  // Exact SLUS_005.61 state-7 body at 0x80016E84. The sole ownership change is the call at
  // 0x80016ED4: the guest libetc VSync body is never entered, while the surrounding stack,
  // registers, command parameters, result inspection, and instruction boundaries remain intact.
  core->r[29] -= 32u;
  core->r[4] = 1u;
  core->r[5] = 0u;
  core->mem_w32(core->r[29] + 28u, core->r[31]);
  core->r[31] = 0x80016E9Cu;
  core->mem_w32(core->r[29] + 24u, core->r[16]);
  psx::cpu::accountGuestInstructions(*core, 6u);
  cdSync(core);

  core->r[3] = kComplete;
  const bool commandReady = core->r[2] == core->r[3];
  core->r[2] = kXaMode;
  psx::cpu::accountGuestInstructions(*core, 3u);
  if (commandReady) {
    core->mem_w8(core->r[29] + 16u, static_cast<std::uint8_t>(core->r[2]));
    core->r[4] = kSetMode;
    core->r[5] = core->r[29] + 16u;
    core->r[16] = kResult;
    core->r[31] = 0x80016EC4u;
    core->r[6] = core->r[16];
    psx::cpu::accountGuestInstructions(*core, 7u);
    cdControl(core);

    const bool commandAccepted = core->r[2] != 0u;
    psx::cpu::accountGuestInstructions(*core, 2u);
    if (commandAccepted) {
      core->r[31] = kSetModeFieldReturn;
      core->r[4] = kSetModeFields;
      psx::cpu::accountGuestInstructions(*core, 2u);
      yieldFields(*core, core->r[31], core->r[4]);

      core->r[2] = core->mem_r8(core->r[16]);
      core->r[3] = kNextState;
      core->mem_w32(kMachineState, core->r[3]);
      core->r[2] &= kStatusError;
      const bool statusOkay = core->r[2] == 0u;
      core->r[2] = 1u;
      psx::cpu::accountGuestInstructions(*core, 7u);
      if (!statusOkay) {
        core->mem_w8(kError, static_cast<std::uint8_t>(core->r[2]));
        psx::cpu::accountGuestInstructions(*core, 2u);
      }
    }
  }

  core->r[31] = core->mem_r32(core->r[29] + 28u);
  core->r[16] = core->mem_r32(core->r[29] + 24u);
  core->r[29] += 32u;
  psx::cpu::accountGuestInstructions(*core, 5u);
}

State::State(Core &core) : core_(core) {}

State::~State() = default;

bool State::dispatchBeforeObjectsB(GuestDispatch dispatch) {
  if (!dispatch) {
    refuse("retained dispatcher is absent");
  }

  if (!transaction_) {
    const bool state7 = core_.mem_r32(kMusicActive) == 2u && core_.mem_r32(kMachineState) == 7u;
    if (!state7) {
      dispatch(&core_, kBeforeObjectsB);
      return true;
    }

    dispatch_ = dispatch;
    transaction_ = std::make_unique<Coro>();
    transaction_->start([this] {
      dispatch_(&core_, kBeforeObjectsB);
    });
  }

  transaction_->resume();
  if (!transaction_->done()) {
    return false;
  }
  transaction_.reset();
  dispatch_ = nullptr;
  return true;
}

void State::yieldFields(std::uint32_t returnAddress, std::uint32_t fields) {
  if (!transaction_ || !transaction_->started() || transaction_->done()) {
    refuse("field yield ran outside the state-7 transaction");
  }
  if (returnAddress != kSetModeFieldReturn || core_.r[31] != returnAddress) {
    refuse("field yield return address is not the binary-authenticated 0x80016ED4 call edge");
  }
  if (fields != kSetModeFields || core_.r[4] != fields) {
    refuse("field yield count is not the binary-authenticated VSync(3) argument");
  }

  for (std::uint32_t field = 0; field < fields; ++field) {
    transaction_->yield();
  }
  core_.r[2] = 0u;
}

bool State::pending() const {
  return transaction_ && !transaction_->done();
}

void registerOverride(Core &core) {
  guest::install(core, kSetModeEntry, "music_stream::setMode", runSetMode);
}

} // namespace x4::music_stream
