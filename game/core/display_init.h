// display_init.h — finite title-owned initialization of X4's two display environments.
#pragma once

#include <cstdint>

class Core;

namespace x4::display_init {

using GuestBody = void (*)(Core *);

inline constexpr std::uint32_t kEntry = 0x800185F8u;

// Preserve the retail display-state publication while omitting its game-owned VSync(0) fence.
void initialize(Core *core,
                GuestBody resetGraph,
                GuestBody clearImage,
                GuestBody drawSync,
                GuestBody setDisplayMask,
                GuestBody publishEnvironment);
void registerOverride(Core &core);

} // namespace x4::display_init
