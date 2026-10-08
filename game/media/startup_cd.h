#pragma once

#include <cstdint>

class Core;

namespace x4::startup_cd {

constexpr std::uint32_t kSetupEntry = 0x80013588u;

using GuestDispatch = void (*)(Core *, std::uint32_t);
using ControllerSetup = void (*)(Core &, std::uint8_t);

// Native func_80013588; dispatch and controller setup are injectable seams.
void run(Core &core, GuestDispatch dispatch, ControllerSetup setupController);
void run(Core *core);
void registerOverride(Core &core);

} // namespace x4::startup_cd
