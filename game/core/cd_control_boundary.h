#pragma once

#include <cstdint>

class Core;

namespace x4::cd_control_boundary {

using GuestBody = void (*)(Core *);
using SynchronousControl = void (*)(Core *);
using ExistingControlPolicy = void (*)(Core *, GuestBody, bool);
using SynchronousSetMode = void (*)(Core &, std::uint8_t);

inline constexpr std::uint32_t kBlockingControl = 0x800E5FF4u;
inline constexpr std::uint32_t kControl = 0x800E5D90u;
inline constexpr std::uint32_t kPauseCommand = 0x09u;
inline constexpr std::uint32_t kSetModeCommand = 0x0Eu;
inline constexpr std::uint32_t kCleanupSetModeReturn = 0x80018ECCu;
inline constexpr std::uint32_t kMusicSetModeReturn = 0x80016EC4u;
inline constexpr std::uint32_t kMusicSetModeResult = 0x80139554u;

// CdControlB is already the retained-super seam for the stock wrapper. Only Pause crosses to the
// synchronous native CD owner; every other command retains the existing loading/retail policy.
void blocking(Core *core,
              GuestBody retailBody,
              SynchronousControl synchronousControl,
              ExistingControlPolicy existingPolicy);

// Cleanup 0x80018E50's exact CdlSetmode call has already paid its authored host-field fence and must
// publish the completed mode through the title's controller authority. Other CdControl callers keep
// the existing fast-wait/retained-super policy.
void control(Core *core,
             GuestBody retailBody,
             ExistingControlPolicy existingPolicy,
             SynchronousSetMode synchronousSetMode);

} // namespace x4::cd_control_boundary
