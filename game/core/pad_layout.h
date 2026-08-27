// pad_layout.h — measured InitPAD receive buffers for SLUS_005.61.
#pragma once

#include "guest_pad_buffer_layout.h"

#include <cstdint>

namespace x4::pad {

// The only InitPAD call in the retail executable passes these two 0x22-byte buffers directly.
// There is no guest pointer table, so host pad service writes the standard packet to the fixed
// addresses. tools/verify_pad.py independently derives both operands from the executable.
inline constexpr std::uint32_t kSlot0Buffer = 0x80166D68u;
inline constexpr std::uint32_t kSlot1Buffer = 0x8012F46Cu;
inline constexpr std::uint32_t kBufferCapacity = 0x22u;
inline constexpr GuestPadBufferLayout kGuestBufferLayout{
    .slot0Buffer = kSlot0Buffer,
    .slot1Buffer = kSlot1Buffer,
};

static_assert(kSlot0Buffer + kBufferCapacity <= kSlot1Buffer || kSlot1Buffer + kBufferCapacity <= kSlot0Buffer);

} // namespace x4::pad
