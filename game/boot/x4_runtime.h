#pragma once

#include "game_runtime.h"
#include "widescreen_controller.h"

namespace x4 {

class X4Runtime final : public GameRuntime {
public:
  X4Runtime();

  // Retail cadence is already 60 fps, so there is nothing to interpolate.
  RenderCapabilities renderCapabilities() const override {
    return RenderCapabilities{
        .defaultPath = RenderPath::Record,
        .nativeRenderPath = false,
        .temporalInterpolation = false,
    };
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
