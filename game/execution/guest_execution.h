#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace x4::guest {

// Enters a guest entry: `callWithoutKnownReturn` or `callWithRegisterReturn` in the product.
using Dispatch = void (*)(Core *, std::uint32_t);

// One retail `jal`: callee, the address after its delay slot, and the guest instructions before it.
struct CallSite {
  std::uint32_t entry;
  std::uint32_t returnAddress;
  std::uint32_t ticks;
};

// Charges the site's instructions, links r[31] and dispatches the callee.
void call(Core &core, Dispatch dispatch, const CallSite &site);

// Entry with no known return address; refuses if the call outlives its first host turn.
void callWithoutKnownReturn(Core *core, std::uint32_t address);

// Caller has already set `core->r[31]`; the link register must resolve in a code image.
void callWithRegisterReturn(Core *core, std::uint32_t address);

// Enter guest code and return the typed boundary; the owner decides how to resume it.
psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address);

} // namespace x4::guest