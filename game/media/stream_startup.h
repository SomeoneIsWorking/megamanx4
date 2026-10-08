#pragma once

#include <cstdint>

class Core;

namespace x4::bios_threads {
class Service;
}

namespace x4::stream_startup {

inline constexpr std::uint32_t kEntry = 0x80018788u;
inline constexpr std::uint32_t kDmaCallbackTable = 0x8011DC5Cu;
inline constexpr std::uint32_t kDmaChannel3CallbackSlot = kDmaCallbackTable + 3u * sizeof(std::uint32_t);
inline constexpr std::uint32_t kStDataReadyCallback = 0x800E8188u;

using GuestDispatch = void (*)(Core *, std::uint32_t);
using FieldService = void (*)(Core &);
using CdTransaction = bool (*)(Core &, std::uint32_t, std::uint32_t, std::uint32_t, FieldService);

// CdRead2's non-wait side effects. The per-channel DMACallback table is 0x8011DC5C; 0x8011CB98 is the
// generic interrupt-class table.
void installReadCallbacks(Core &core, std::uint32_t readMode);

// FieldService for startup commands: yields the retail task until the next field.
void awaitField(Core &core);
void awaitField(Core &core, bios_threads::Service &threads);

// Native SLUS_005.61 STR/MDEC startup; hardware waits go through the injected services.
void run(Core &core, GuestDispatch dispatch, FieldService serviceField, CdTransaction startCdStream);
void run(Core *core);
void registerOverride(Core &core);

} // namespace x4::stream_startup
