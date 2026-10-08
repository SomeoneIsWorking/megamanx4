#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace x4::guest {

// Entry with no known return address; refuses if the call outlives its first host turn.
void callWithoutKnownReturn(Core *core, std::uint32_t address);

// Caller has already set `core->r[31]`; the link register must resolve in a code image.
void callWithRegisterReturn(Core *core, std::uint32_t address);

// Enter guest code and return the typed boundary; the owner decides how to resume it.
psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address);

} // namespace x4::guest