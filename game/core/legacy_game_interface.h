#pragma once

struct GameConfig;
struct GameHooks;
struct GuestProgramImage;

namespace x4::legacy {

// These measured tables are compatibility debt for generic framework algorithms that still read
// Core::cfg/Core::hooks. X4Runtime is the title's public ownership seam; no new behavior or facts
// belong in these tables while the framework migrates them into narrow typed interfaces.
extern const GameConfig &measuredConfig;
extern const GameHooks &compatibilityHooks;
extern const GuestProgramImage &measuredProgramImage;

} // namespace x4::legacy
