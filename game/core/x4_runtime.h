#pragma once

#include "game_iface.h"
#include "render_mode.h"

namespace x4 {

// Process-lifetime owner of Mega Man X4's framework-facing behavior. The legacy base is temporary:
// it keeps measured compatibility facts reachable while shared algorithms migrate off GameConfig.
class X4Runtime final : public LegacyGameRuntimeAdapter {
public:
  X4Runtime();

  bool configureRenderPath();

  static constexpr RenderPath requiredRenderPath() {
    return RenderPath::Gte;
  }

  static constexpr bool supportsRenderPath(RenderPath path) {
    return path == RenderPath::Gte || path == RenderPath::Psx;
  }

  void registerOverrides(Game &game) override;
  void bootInit(Core &core) override;
};

} // namespace x4
