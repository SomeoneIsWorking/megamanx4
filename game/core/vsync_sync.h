// vsync_sync.h — Mega Man X4's measured libetc VBlank synchronization seam.
#pragma once

#include <cstdint>

class Game;

namespace x4::vsync {

// Retail SLUS_005.61, SHA-1 213733031136d095ca275d6957695aa25011cfa5.
// 0x800E4EF8 is the helper called twice by libetc VSync: it waits until the IRQ-owned counter
// reaches a0. 0x800E4F94 is the next function entry, so this half-open interval is the helper's
// exact executable body rather than a broad library window.
inline constexpr uint32_t kWait = 0x800E4EF8u;
inline constexpr uint32_t kWaitEnd = 0x800E4F94u;

void install(Game *game);

} // namespace x4::vsync
