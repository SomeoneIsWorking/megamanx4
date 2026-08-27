#include "core.h"
#include "game.h"
#include "startup_cd.h"

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
std::size_t g_controllerOrder = 0;
std::uint8_t g_controllerMode = 0;

void recordDispatch(Core *core, std::uint32_t entry) {
  g_calls.push_back({entry, core->r[31], core->r[4], core->r[5]});
  switch (entry) {
  case 0x800E5D60u:
    core->r[2] = core->mem_r32(0x8011DD1Cu);
    core->mem_w32(0x8011DD1Cu, core->r[4]);
    break;
  case 0x800E5D78u:
    core->r[2] = core->mem_r32(0x8011DD20u);
    core->mem_w32(0x8011DD20u, core->r[4]);
    break;
  case 0x800E8004u:
    core->r[2] = core->mem_r32(0x8011E028u);
    core->mem_w32(0x8011E028u, core->r[4]);
    break;
  case 0x80016334u:
    core->r[2] = 0x16334u;
    break;
  default:
    break;
  }
}

void recordController(Core &, std::uint8_t mode) {
  g_controllerOrder = g_calls.size();
  g_controllerMode = mode;
}

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_startup_cd: %s\n", message);
  }
  return condition;
}

bool verifyCallOrder() {
  constexpr std::array<std::uint32_t, 9> kEntries = {
      0x800EDC74u,
      0x800EDCCCu,
      0x800E4F94u,
      0x800E4FC4u,
      0x800E7398u,
      0x800E5D60u,
      0x800E5D78u,
      0x800E8004u,
      0x80016334u,
  };
  constexpr std::array<std::uint32_t, 9> kReturnAddresses = {
      0x800E74F4u,
      0x800E750Cu,
      0x800E7544u,
      0x800E7554u,
      0x800E5C60u,
      0x800E5B00u,
      0x800E5B10u,
      0x800E5B20u,
      0x80013604u,
  };

  if (!check(g_calls.size() == kEntries.size(), "finite setup dispatched the wrong number of guest leaves")) {
    return false;
  }
  for (std::size_t index = 0; index < kEntries.size(); ++index) {
    if (!check(g_calls[index].entry == kEntries[index], "finite setup changed retail guest-call order") ||
        !check(g_calls[index].returnAddress == kReturnAddresses[index],
               "finite setup changed a measured retail return edge")) {
      return false;
    }
  }

  return check(g_controllerOrder == 8u, "controller mode was not published between callbacks and title state") &&
         check(g_controllerMode == 0xA0u, "controller received a non-retail startup mode") &&
         check(g_calls[0].a0 == 0x80011BF4u, "CD_init primary diagnostic string changed") &&
         check(g_calls[1].a0 == 0x80011C00u && g_calls[1].a1 == 0x8011DFFCu,
               "CD_init register diagnostic arguments changed") &&
         check(g_calls[3].a0 == 2u && g_calls[3].a1 == 0x800E7944u, "CD interrupt hook arguments changed") &&
         check(g_calls[5].a0 == 0x800E5B5Cu && g_calls[6].a0 == 0x800E5B84u && g_calls[7].a0 == 0x800E5BACu,
               "initial libcd callback addresses changed");
}

bool verifyPublishedState(Core &core, std::uint32_t initialStack, std::uint32_t initialReturnAddress) {
  constexpr std::array<std::uint32_t, 7> kTitleBytes = {
      0x80137CE4u,
      0x801406ACu,
      0x8013BD40u,
      0x801374B8u,
      0x801374B4u,
      0x80137CF0u,
      0x80137CF4u,
  };

  bool stateMatches =
      check(core.r[29] == initialStack, "finite setup did not restore the caller stack") &&
      check(core.r[31] == initialReturnAddress, "finite setup did not restore caller RA") &&
      check(core.mem_r8(initialStack - 16u) == 0xA0u,
            "finite setup did not preserve the retail stack-local mode byte") &&
      check(core.r[2] == 0x16334u, "finite setup did not preserve the final title initializer's register leaf") &&
      check(core.mem_r8(0x8011DD3Cu) == 0u && core.mem_r8(0x8011DD3Du) == 0u,
            "finite setup did not reset libcd command bytes") &&
      check(core.mem_r32(0x8011DD2Cu) == 0u && core.mem_r32(0x8011DD30u) == 0u,
            "finite setup did not reset libcd command words") &&
      check(core.mem_r32(0x8011DD1Cu) == 0x800E5B5Cu && core.mem_r32(0x8011DD20u) == 0x800E5B84u &&
                core.mem_r32(0x8011E028u) == 0x800E5BACu,
            "finite setup did not publish the three initial libcd callbacks");
  for (const std::uint32_t address : kTitleBytes) {
    stateMatches =
        check(core.mem_r8(address) == 0u, "finite setup did not clear a retail title CD byte") && stateMatches;
  }
  return stateMatches;
}

bool verifyNoGuestSynchronization() {
  for (const Call &call : g_calls) {
    if (!check(call.entry != 0x800E4DB0u, "finite setup dispatched guest VSync") ||
        !check(call.entry != 0x800E5ACCu, "finite setup dispatched polling CdInit") ||
        !check(call.entry != 0x800E5D90u, "finite setup dispatched polling CdControl")) {
      return false;
    }
  }
  return true;
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  constexpr std::uint32_t kInitialStack = 0x801FFF00u;
  constexpr std::uint32_t kInitialReturnAddress = 0x81234567u;
  core.r[29] = kInitialStack;
  core.r[31] = kInitialReturnAddress;

  constexpr std::array<std::uint32_t, 13> kDirtyWords = {
      0x8011DD1Cu,
      0x8011DD20u,
      0x8011DD2Cu,
      0x8011DD30u,
      0x8011DD3Cu,
      0x8011DD3Du,
      0x8011E028u,
      0x80137CE4u,
      0x801406ACu,
      0x8013BD40u,
      0x801374B8u,
      0x801374B4u,
      0x80137CF0u,
  };
  for (const std::uint32_t address : kDirtyWords) {
    core.mem_w32(address, 0xA5A5A5A5u);
  }
  core.mem_w32(0x80137CF4u, 0xA5A5A5A5u);

  g_calls.clear();
  g_controllerOrder = 0;
  g_controllerMode = 0;
  x4::startup_cd::run(core, recordDispatch, recordController);

  if (!verifyCallOrder() || !verifyPublishedState(core, kInitialStack, kInitialReturnAddress) ||
      !verifyNoGuestSynchronization()) {
    return 1;
  }
  std::puts("x4_startup_cd: finite native CD setup state and exact retail leaf order passed");
  return 0;
}
