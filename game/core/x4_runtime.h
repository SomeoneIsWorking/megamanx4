#pragma once

#include "game_iface.h"
#include "render_mode.h"

#include <string_view>

namespace x4 {

// Process-lifetime owner of Mega Man X4's framework-facing behavior. The legacy base is temporary:
// it keeps measured compatibility facts reachable while shared algorithms migrate off GameConfig.
class X4Runtime final : public LegacyGameRuntimeAdapter {
public:
  X4Runtime();

  bool configureRenderPath();
  bool validateRenderEnhancements() const;

  // X4's retail update/display cadence is already the target cadence. Widescreen therefore owns
  // only projection/culling/presentation work; it must not pull in the framework's interpolated-frame
  // pipeline or either of that pipeline's native-render prerequisites.
  static constexpr std::string_view executableId() {
    return "SLUS_005.61";
  }
  static constexpr bool targetsWidescreen() {
    return true;
  }
  static constexpr bool supportsTemporalInterpolation() {
    return false;
  }
  static constexpr bool requiresNativeDepth() {
    return false;
  }
  static constexpr bool requiresNativeProducers() {
    return false;
  }

  static constexpr RenderPath requiredRenderPath() {
    return RenderPath::Gte;
  }

  static constexpr bool supportsRenderPath(RenderPath path) {
    return path == RenderPath::Gte || path == RenderPath::Psx;
  }

  void *createContext(Core &core) override;
  void destroyContext(void *context) override;
  void registerOverrides(Game &game) override;
  void bootInit(Core &core) override;
};

} // namespace x4
