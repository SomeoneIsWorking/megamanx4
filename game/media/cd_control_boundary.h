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

// Only Pause goes to the synchronous native CD owner; other commands keep the existing policy.
void blocking(Core *core,
              GuestBody retailBody,
              SynchronousControl synchronousControl,
              ExistingControlPolicy existingPolicy);

// Owned CdlSetmode calls (cleanup 0x80018E50, music state 7) publish through the title controller;
// other callers keep the existing policy.
void control(Core *core,
             GuestBody retailBody,
             ExistingControlPolicy existingPolicy,
             SynchronousSetMode synchronousSetMode);

} // namespace x4::cd_control_boundary
