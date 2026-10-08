#pragma once

#include <cstdint>

class Core;

namespace x4::cd_controller {

inline constexpr std::uint8_t kLibCdInterruptMask = 0x07u;

// Clear libcd command/callback bookkeeping in guest RAM; separate from the controller reset.
void clearCommandState(Core &core);

// Completed state of the stock CdReset; keeps the controller's disc/XA/clock bindings.
void reset(Core &core);

// Publish the completed CdlSetmode state to both native controller and XA owners.
void setMode(Core &core, std::uint8_t mode);

} // namespace x4::cd_controller
