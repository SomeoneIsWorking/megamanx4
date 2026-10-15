// InitPAD receive buffers for SLUS_005.61.
#pragma once

#include <cstdint>

namespace x4::pad {

// The only InitPAD call passes these two 0x22-byte buffers directly, so the host writes the packet there.
inline constexpr std::uint32_t kSlot0Buffer = 0x80166D68u;
inline constexpr std::uint32_t kSlot1Buffer = 0x8012F46Cu;
inline constexpr std::uint32_t kBufferCapacity = 0x22u;

static_assert(kSlot0Buffer + kBufferCapacity <= kSlot1Buffer || kSlot1Buffer + kBufferCapacity <= kSlot0Buffer);

} // namespace x4::pad
