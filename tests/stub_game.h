// stub_game.h — a Game around psxport's stub runtime, for a test of one X4 owner.
#pragma once

#include "game.h"
#include "stock_libcd.h"
#include "stub_game_runtime.h"

#include <memory>

namespace x4::test {

class StubGame {
public:
  StubGame() : game_(std::make_unique<Game>(runtime_, psx::config::Config{})) {}

  Game &game() {
    return *game_;
  }
  Core &core() {
    return game_->core;
  }
  // x4::Runtime's libcd: guest code whose bodies the title's CD wrappers call.
  const psx::cd::StockLibcd &libcd() const {
    return libcd_;
  }

private:
  psx::test::StubGameRuntime runtime_;
  std::unique_ptr<Game> game_;
  psx::cd::StockLibcd libcd_{{}, {}, 0};
};

} // namespace x4::test
