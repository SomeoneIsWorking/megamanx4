#pragma once

#include "game_runtime.h"
#include "widescreen_controller.h"

namespace x4 {

// Process-lifetime owner of Mega Man X4's framework-facing behavior. It derives the narrow runtime
// seam directly: the legacy GameConfig/GameHooks tables are compatibility views for unmigrated
// generic algorithms, not a behavior-bearing base class and not a source of temporal policy.
class X4Runtime final : public GameRuntime {
public:
  X4Runtime();

  // X4's retail update/display cadence is already the target cadence. Widescreen therefore owns
  // only projection/culling/presentation work; it must not pull in the framework's interpolated-frame
  // pipeline or either of that pipeline's native-render prerequisites.
  RenderCapabilities renderCapabilities() const override {
    return RenderCapabilities::widescreenOnly();
  }

  void *createContext(Core &core) override;
  void destroyContext(void *context) override;
  void registerOverrides(Game &game) override;
  void bootInit(Core &core) override;
  std::unique_ptr<FrameDriver> createFrameDriver(Game &game) override;
  const GuestPadBufferLayout *guestPadBufferLayout() const override;
  const GuestProgramImage *guestProgramImage() const override;
  bool guestVramIsPicture(const Game &game) const override;
  const GuestWidescreenProjection *guestWidescreenProjection() const override;

private:
  WidescreenPolicy widescreenPolicy_;
};

} // namespace x4
