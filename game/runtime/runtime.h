#pragma once

#include "game_runtime.h"
#include "stock_dma_callbacks.h"
#include "stock_libcd.h"
#include "stock_pad_buffers.h"
#include "stock_vsync.h"
#include "widescreen_controller.h"

namespace x4 {

// Process-lifetime owner of Mega Man X4: replays crt0 and the gameMain prefix, then x4::frame::FrameDriver owns
// each field. Retail cadence is already 60 fps, so nothing is interpolated.
class Runtime final : public psx::game::GameRuntime {
public:
  Runtime();

  void startProgram(Core &core) override;
  void registerOverrides(Game &game) override;
  std::unique_ptr<psx::game::TitleSessionState> createSession(Game &game) override;
  std::unique_ptr<psx::game::FrameDriver> createFrameDriver(Game &game) override;
  void deliverPad(Core &core, const psx::input::PadDelivery &delivery) override;
  RenderCapabilities renderCapabilities() const override;
  bool guestVramIsPicture(const Game &game) const override;
  const GuestWidescreenProjection *guestWidescreenProjection() const override;
  bool titleCommand(Core &core, const psx::game::TitleCommandLine &input, std::FILE *reply) override;
  psx::game::TitleDevWarp *devWarp(Core &core) const override;
  void reportRun(Core &core) const override;
  const psx::game::HostIdentity *hostIdentity() const override;

private:
  psx::hle::StockVSync vsync_;
  psx::hle::StockDmaCallbacks dmaCallbacks_;
  psx::cd::StockLibcd libcd_;
  psx::input::StockPadBuffers pad_;
  WidescreenPolicy widescreenPolicy_;
};

} // namespace x4
