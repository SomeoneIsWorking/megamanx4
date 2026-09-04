#include "guest_execution.h"

#include "core.h"
#include "execution_exit.h"
#include "native_dispatch.h"

#include <cstdlib>
#include <lucent/log.h>

namespace x4::guest {
namespace {

psx::cpu::NativeKey keyFor(Core &core, std::uint32_t address, const char *owner) {
  const auto image = core.currentImageIdentity(address);
  if (!image) {
    lucent::error("x4-guest", "{} has no authenticated image identity for guest address 0x{:08X}", owner, address);
    std::abort();
  }
  return {*image, address};
}

void requireReturn(const psx::cpu::ExecutionResult &result, const char *owner) {
  if (!psx::cpu::requireGuestReturn(result, owner)) {
    std::abort();
  }
}

} // namespace

void call(Core *core, std::uint32_t address) {
  if (!core) {
    lucent::error("x4-guest", "guest call 0x{:08X} received a null Core", address);
    std::abort();
  }
  requireReturn(dispatch(*core, address), "Mega Man X4 guest call");
}

psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address) {
  return psx::cpu::dispatchGuest(core, address, psx::cpu::ExecutionBudget::currentTurn(core));
}

void callOriginal(Core *core, std::uint32_t address, const char *owner) {
  if (!core) {
    lucent::error("x4-guest", "{} received a null Core", owner);
    std::abort();
  }
  requireReturn(
      psx::cpu::callOriginal(*core, keyFor(*core, address, owner), psx::cpu::ExecutionBudget::currentTurn(*core)),
      owner);
}

void install(Core &core, std::uint32_t address, const char *name, NativeFunction function) {
  if (!function) {
    lucent::error("x4-guest", "{} has no native implementation", name);
    std::abort();
  }
  if (!core.nativeDispatcher().install({keyFor(core, address, name), name, function})) {
    lucent::error("x4-guest", "{} could not install its native override", name);
    std::abort();
  }
}

} // namespace x4::guest
