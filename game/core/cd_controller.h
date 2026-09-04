#pragma once

#include <cstdint>

class Core;

namespace x4::cd_controller {

inline constexpr std::uint8_t kLibCdInterruptMask = 0x07u;

// Clear the stock libcd command/callback bookkeeping written by CD_init/CdReset. This is guest RAM
// state, independent of the native controller object's reset.
void clearCommandState(Core &core);

// Title-local completed state for the stock CdReset transaction. Preserve the controller's bound
// disc/XA/clock wiring while clearing transient command and stream state.
void reset(Core &core);

// Publish the completed CdlSetmode state to both native controller and XA owners.
void setMode(Core &core, std::uint8_t mode);

} // namespace x4::cd_controller
