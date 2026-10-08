#pragma once

struct GameConfig;
struct GameHooks;
struct GuestProgramImage;

namespace x4::legacy {

// Compatibility views for framework code still reading Core::cfg / Core::hooks.
const GameConfig &measuredConfig();
const GameHooks &compatibilityHooks();
const GuestProgramImage &measuredProgramImage();

} // namespace x4::legacy
