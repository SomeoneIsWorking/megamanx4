#pragma once

#include <cstdint>

class Core;

namespace x4::stream_interrupt {

inline constexpr std::uint32_t kEntry = 0x800E84D8u;
inline constexpr std::uint32_t kCdReadyReturn = 0x800E856Cu;

using GuestBody = void (*)(Core *);

// Own the libstr sector-completion boundary while retaining the original StCdInterrupt guest body. The
// enclosing libcd callback has already consumed the controller interrupt and supplies its status and
// response in a0/a1; the scoped CdReady seam prevents that body from querying the completed command
// again through libcd's VSync-based timeout loop.
void run(Core &core, GuestBody retailBody);
void run(Core *core);

// Called by the title's sole CdReady override before its synchronous-loader policy. Returns true only
// for StCdInterrupt's measured CdReady(1, sp+48) edge while run() owns the stack.
bool consumeCompletedCallback(Core &core);

void registerOverride(Core &core);

} // namespace x4::stream_interrupt
