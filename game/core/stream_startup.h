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

// Preserve CdRead2's non-wait callback/sector-framing publications. This writes the per-channel
// DMACallback table at 0x8011DC5C; the similarly numbered 0x8011CB98 table is the generic interrupt
// class table and must not be used for channel dispatch.
void installReadCallbacks(Core &core, std::uint32_t readMode);

// Suspend the current retail task until the native frame shell begins the next field. This is the
// shipping FieldService for startup command phases; it never advances peripherals or presentation
// itself.
void awaitField(Core &core);
void awaitField(Core &core, bios_threads::Service &threads);

// Finite native owner of SLUS_005.61's STR/MDEC startup. The authenticated guest executable remains
// the source for ordinary calls. The injected services keep hardware synchronization outside guest
// libcd/libetc while the native frame shell remains the sole field/presentation owner.
void run(Core &core, GuestDispatch dispatch, FieldService serviceField, CdTransaction startCdStream);
void run(Core *core);
void registerOverride(Core &core);

} // namespace x4::stream_startup
