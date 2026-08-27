// vsync_sync.h — Mega Man X4's native-owned display-field service.
#pragma once

#include <cstdint>

class Core;

namespace x4::vsync {

// Retail SLUS_005.61, SHA-1 213733031136d095ca275d6957695aa25011cfa5.
// Full libetc VSync entry. The native frame shell owns timing, so every guest call and every mode is
// forbidden. The half-open four-byte window admits only this measured entry to PlatformHle.
inline constexpr uint32_t kVSync = 0x800E4DB0u;
inline constexpr uint32_t kVSyncEntryEnd = 0x800E4DB4u;

// Advance exactly one retail display field at the native frame boundary.
void deliverField(Core &core);

} // namespace x4::vsync
