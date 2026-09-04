// gpu_timeout.h — native owner of PsyQ's field-relative GPU timeout deadline.
#pragma once

#include <cstdint>

class Core;

namespace x4::gpu_timeout {

inline constexpr std::uint32_t kSetAlarmEntry = 0x800ECB38u;

// Preserve set_alarm's guest-visible state while sourcing its counter directly from the field owner.
void setAlarm(Core *core);
void registerOverride(Core &core);

} // namespace x4::gpu_timeout
