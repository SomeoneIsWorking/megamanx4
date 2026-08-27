#include "startup_cd.h"

#include "c_subsys.h"
#include "cdc_state.h"
#include "cfg.h"
#include "core.h"
#include "game.h"
#include "override_registry.h"

#include <cstdlib>
#include <lucent/log.h>

#ifdef MMX4_HAVE_SUBSTRATE
extern void gen_func_80013588(Core *);
extern void shard_set_override(std::uint32_t, void (*)(Core *));
#endif

namespace x4::startup_cd {
namespace {

// Retail func_80013588 and its successful CdInit/CdReset chain. Addresses and call edges are
// measured from generated/shard_{0,1,2,3,5}.c; the matching decomp is external/mmx4/src/main/323C.c.
constexpr std::uint32_t kCdInitLog = 0x800EDC74u;
constexpr std::uint32_t kCdInitLogDetail = 0x800EDCCCu;
constexpr std::uint32_t kResetCallback = 0x800E4F94u;
constexpr std::uint32_t kInterruptCallback = 0x800E4FC4u;
constexpr std::uint32_t kCdInitVolume = 0x800E7398u;
constexpr std::uint32_t kCdSyncCallback = 0x800E5D60u;
constexpr std::uint32_t kCdReadyCallback = 0x800E5D78u;
constexpr std::uint32_t kCdReadCallback = 0x800E8004u;
constexpr std::uint32_t kInitializeTitleCdState = 0x80016334u;

constexpr std::uint32_t kCdInitLogString = 0x80011BF4u;
constexpr std::uint32_t kCdInitDetailString = 0x80011C00u;
constexpr std::uint32_t kCdRegisterPointers = 0x8011DFFCu;
constexpr std::uint32_t kCdInterruptHandler = 0x800E7944u;
constexpr std::uint32_t kInitialSyncCallback = 0x800E5B5Cu;
constexpr std::uint32_t kInitialReadyCallback = 0x800E5B84u;
constexpr std::uint32_t kInitialReadCallback = 0x800E5BACu;

constexpr std::uint32_t kSyncCallbackSlot = 0x8011DD1Cu;
constexpr std::uint32_t kReadyCallbackSlot = 0x8011DD20u;
constexpr std::uint32_t kCommandResult = 0x8011DD2Cu;
constexpr std::uint32_t kCommandStatus = 0x8011DD30u;
constexpr std::uint32_t kLastInterrupt = 0x8011DD3Cu;
constexpr std::uint32_t kLastCommand = 0x8011DD3Du;

constexpr std::uint32_t kLoadState = 0x801406ACu;
constexpr std::uint32_t kArchivePostprocessPending = 0x8013BD40u;
constexpr std::uint32_t kCdStateA = 0x80137CE4u;
constexpr std::uint32_t kCdStateB = 0x801374B8u;
constexpr std::uint32_t kCdStateC = 0x801374B4u;
constexpr std::uint32_t kArchiveProcessedCount = 0x80137CF0u;
constexpr std::uint32_t kArchiveEnqueuedCount = 0x80137CF4u;

constexpr std::uint8_t kRetailMode = 0xA0u;
constexpr std::uint8_t kLibCdInterruptMask = 0x07u;

void call(Core &core,
          GuestDispatch dispatch,
          std::uint32_t entry,
          std::uint32_t returnAddress,
          std::uint32_t a0,
          std::uint32_t a1) {
  core.r[4] = a0;
  core.r[5] = a1;
  core.r[31] = returnAddress;
  dispatch(&core, entry);
}

void setupNativeController(Core &core, std::uint8_t mode) {
  if (!core.game) {
    cfg_loge("x4-startup-cd", "func_80013588 requires a bound Game");
    std::abort();
  }

  // CD_init's reset/demute command train returns the drive to its ready state with no command or
  // response pending. Use the controller's one power-on/reset authority, preserving its Game wiring
  // and injected clock, then publish the bank-1 interrupt mask and completed Setmode state directly.
  // No guest command is pending and no polling clock is borrowed.
  CdcState &controller = core.game->cdc;
  XaState *const xa = controller.xa;
  void *const tickContext = controller.tick_context;
  const CdcTickNowFn tickNow = controller.tick_now;
  cdc_state_init(&controller);
  controller.xa = xa;
  cdc_bind_tick_source(&controller, tickContext, tickNow);
  controller.irq_en = kLibCdInterruptMask;
  xa_stream_setmode(&core.game->xa, mode);
  cdc_set_mode(&controller, mode);
}

} // namespace

void run(Core &core, GuestDispatch dispatch, ControllerSetup setupController) {
  if (!dispatch || !setupController) {
    cfg_loge("x4-startup-cd", "func_80013588 requires finite dispatch and controller services");
    std::abort();
  }

  // Preserve the retail activation. The final title initializer is allowed to use this caller's
  // local frame and the override leaves SP/RA exactly as gen_func_80013588 does.
  core.r[29] -= 32u;
  core.mem_w32(core.r[29] + 24u, core.r[31]);
  core.mem_w8(core.r[29] + 16u, kRetailMode);

  // CD_init's diagnostic calls precede all state mutation on the successful retail path.
  call(core, dispatch, kCdInitLog, 0x800E74F4u, kCdInitLogString, core.r[5]);
  call(core, dispatch, kCdInitLogDetail, 0x800E750Cu, kCdInitDetailString, kCdRegisterPointers);

  // These are the complete libcd RAM resets performed before the hardware command/alarm chain.
  // The command train is replaced below by the already-native controller's completed ready state.
  core.mem_w8(kLastCommand, 0u);
  core.mem_w8(kLastInterrupt, 0u);
  core.mem_w32(kReadyCallbackSlot, 0u);
  core.mem_w32(kSyncCallbackSlot, 0u);
  core.mem_w32(kCommandStatus, 0u);
  core.mem_w32(kCommandResult, 0u);

  call(core, dispatch, kResetCallback, 0x800E7544u, core.r[4], core.r[5]);
  call(core, dispatch, kInterruptCallback, 0x800E7554u, 2u, kCdInterruptHandler);

  // CdReset(1) initializes the CD/SPU volume registers after CD_init reports success.
  call(core, dispatch, kCdInitVolume, 0x800E5C60u, core.r[4], core.r[5]);

  // CdInit publishes the title's three callbacks only after reset and volume initialization.
  call(core, dispatch, kCdSyncCallback, 0x800E5B00u, kInitialSyncCallback, core.r[5]);
  call(core, dispatch, kCdReadyCallback, 0x800E5B10u, kInitialReadyCallback, core.r[5]);
  call(core, dispatch, kCdReadCallback, 0x800E5B20u, kInitialReadCallback, core.r[5]);

  // Retail next loops on CdControl(CdlSetmode, 0xA0) and calls VSync(3). Both are synchronization
  // mechanics. The native controller owns completion and publishes mode to both data and XA paths;
  // no libetc VSync query or wait is executed or treated as successful.
  setupController(core, kRetailMode);

  core.mem_w8(kCdStateA, 0u);
  core.mem_w8(kLoadState, 0u);
  core.mem_w8(kArchivePostprocessPending, 0u);
  core.mem_w8(kCdStateB, 0u);
  core.mem_w8(kCdStateC, 0u);
  core.mem_w8(kArchiveProcessedCount, 0u);
  core.mem_w8(kArchiveEnqueuedCount, 0u);
  call(core, dispatch, kInitializeTitleCdState, 0x80013604u, core.r[4], core.r[5]);

  core.r[31] = core.mem_r32(core.r[29] + 24u);
  core.r[29] += 32u;
}

void run(Core *core) {
  if (!core) {
    cfg_loge("x4-startup-cd", "func_80013588 received a null Core");
    std::abort();
  }
  run(*core, rec_dispatch, setupNativeController);
}

void registerOverride() {
#ifdef MMX4_HAVE_SUBSTRATE
  overrides::install(
      kSetupEntry, "startup::initializeCd", static_cast<void (*)(Core *)>(run), gen_func_80013588, shard_set_override);
#else
  lucent::debug("x4-startup-cd", "startup CD ownership registration deferred: no generated substrate");
#endif
}

} // namespace x4::startup_cd
