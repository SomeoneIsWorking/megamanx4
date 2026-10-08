#pragma once

#include <cstdint>

class Core;

namespace x4::stream_interrupt {

inline constexpr std::uint32_t kEntry = 0x800E84D8u;
inline constexpr std::uint32_t kCdReadyReturn = 0x800E856Cu;

using GuestBody = void (*)(Core *);

// Wraps the original StCdInterrupt body. a0/a1 carry the libcd status and response; the scoped
// CdReady seam stops the body re-querying the command through libcd's VSync timeout loop.
void run(Core &core, GuestBody retailBody);
void run(Core *core);

// Called from the CdReady override; true only for StCdInterrupt's CdReady(1, sp+48) while run() is active.
bool consumeCompletedCallback(Core &core);

void registerOverride(Core &core);

} // namespace x4::stream_interrupt
