// Display-field service and the owner of the libetc VSync entry 0x800E4DB0.
#pragma once

#include <cstdint>

class Core;

namespace x4::bios_threads {
class Service;
}

namespace x4::vsync {

// Full libetc VSync entry and its half-open four-byte window; every mode is served as retail decodes it.
inline constexpr std::uint32_t kVSync = 0x800E4DB0u;
inline constexpr std::uint32_t kVSyncEntryEnd = 0x800E4DB4u;

// kVblankCounter: incremented per field by the IRQ-0 handler 0x800E56FC; kRegisterCell0/1 hold GPUSTAT
// 0x1F801814 and root counter 1 0x1F801110; kLastSample/kLastSync are the previous RCNT1 sample and
// the counter at the last sync.
inline constexpr std::uint32_t kVblankCounter = 0x8011DC50u;
inline constexpr std::uint32_t kRegisterCell0 = 0x8011CB84u;
inline constexpr std::uint32_t kRegisterCell1 = 0x8011CB88u;
inline constexpr std::uint32_t kLastSample = 0x8011CB8Cu;
inline constexpr std::uint32_t kLastSync = 0x8011CB90u;

// mode < 0 and mode == 1 wait nothing; mode 0 waits one field; mode >= 2 waits `mode` fields (0x800E4E00).
// a1 is only the helper's spin budget (0x800E4EFC), never a field count.
inline constexpr std::uint32_t fieldsForMode(std::int32_t mode) {
  return mode == 1 ? 0u : (mode == 0 ? 1u : static_cast<std::uint32_t>(mode));
}

// Advance exactly one retail display field at the native frame boundary.
void deliverField(Core &core);

// Park one host field and leave VSync(0)'s unconsumed zero in v0; `returnAddress` must equal r[31].
void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads);

void serveVSync(Core *core);

// Install `serveVSync` as the image-scoped owner of the entry; `.vsyncTrap` stays as the fail-fast backstop.
void registerOverrides(Core &core);

} // namespace x4::vsync
