#pragma once

#include "execution_exit.h"

#include <cstdint>

class Core;

namespace x4::guest {

using NativeFunction = void (*)(Core *);

// Enter one authenticated guest function through the product Lightrec dispatcher and require its
// ordinary return. Typed frame/yield/fault exits remain explicit at their owning boundaries.
void call(Core *core, std::uint32_t address);

// Enter guest code while preserving a typed execution boundary for the host owner to handle.
psx::cpu::ExecutionResult dispatch(Core &core, std::uint32_t address);

// Enter the original guest body while suppressing only the currently selected native override.
void callOriginal(Core *core, std::uint32_t address, const char *owner);

// Register a title-native function against the active authenticated image identity.
void install(Core &core, std::uint32_t address, const char *name, NativeFunction function);

} // namespace x4::guest
