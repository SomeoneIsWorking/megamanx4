#pragma once

#include <cstdint>

class Core;

namespace x4::startup_cd {

constexpr std::uint32_t kSetupEntry = 0x80013588u;

using GuestDispatch = void (*)(Core *, std::uint32_t);
using ControllerSetup = void (*)(Core &, std::uint8_t);

// Finite native owner of func_80013588. The retail body remains registered as the generated super;
// this operation exposes its two host-owned seams so the exact guest-call order and published state
// can be checked without running the controller's asynchronous command machinery.
void run(Core &core, GuestDispatch dispatch, ControllerSetup setupController);
void run(Core *core);
void registerOverride();

} // namespace x4::startup_cd
