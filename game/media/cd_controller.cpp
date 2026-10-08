#include "cd_controller.h"

#include "c_subsys.h"
#include "cdc_state.h"
#include "cfg.h"
#include "core.h"
#include "game.h"

#include <cstdlib>

namespace x4::cd_controller {
namespace {

constexpr std::uint32_t kSyncCallbackSlot = 0x8011DD1Cu;
constexpr std::uint32_t kReadyCallbackSlot = 0x8011DD20u;
constexpr std::uint32_t kCommandResult = 0x8011DD2Cu;
constexpr std::uint32_t kCommandStatus = 0x8011DD30u;
constexpr std::uint32_t kLastInterrupt = 0x8011DD3Cu;
constexpr std::uint32_t kLastCommand = 0x8011DD3Du;

} // namespace

void clearCommandState(Core &core) {
  core.mem_w8(kLastCommand, 0u);
  core.mem_w8(kLastInterrupt, 0u);
  core.mem_w32(kReadyCallbackSlot, 0u);
  core.mem_w32(kSyncCallbackSlot, 0u);
  core.mem_w32(kCommandStatus, 0u);
  core.mem_w32(kCommandResult, 0u);
}

void reset(Core &core) {
  if (!core.game) {
    cfg_loge("x4-cd-controller", "native controller reset requires a bound Game");
    std::abort();
  }

  CdcState &controller = core.game->cdc;
  XaState *const xa = controller.xa;
  void *const tickContext = controller.tick_context;
  const CdcTickNowFn tickNow = controller.tick_now;
  cdc_state_init(&controller);
  controller.xa = xa;
  cdc_bind_tick_source(&controller, tickContext, tickNow);
  controller.irq_en = kLibCdInterruptMask;

  core.game->cd.stock_reading = 0;
  core.game->cd.stream_active = 0;
  xa_stream_stop(&core.game->xa);
}

void setMode(Core &core, std::uint8_t mode) {
  if (!core.game) {
    cfg_loge("x4-cd-controller", "native controller mode publication requires a bound Game");
    std::abort();
  }
  xa_stream_setmode(&core.game->xa, mode);
  cdc_set_mode(&core.game->cdc, mode);
}

} // namespace x4::cd_controller
