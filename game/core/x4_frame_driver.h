#pragma once

#include "game_runtime.h"

#include <cstdint>

class Core;

namespace x4::frame {

using GuestDispatch = void (*)(Core *, std::uint32_t);
using FieldService = void (*)(Core &);
using PresentationSync = void (*)(Core &);

// Execute the finite prefix of retail gameMain 0x80012024. The framework frame shell calls this
// once, then owns repetition through X4FrameDriver; the guest's VSync loop is never entered.
void bootPrefix(Core &core, GuestDispatch dispatch);
void bootPrefix(Core &core);

// One native-owned iteration of the retail main loop, with VSync replaced by the title's measured
// field boundary. Every remaining guest leaf stays on the generated dispatch path.
class X4FrameDriver final : public FrameDriver {
public:
  X4FrameDriver(GuestDispatch dispatch, FieldService fieldService, PresentationSync presentationSync = nullptr);
  X4FrameDriver();

  void stepFrame(Core &core, std::uint32_t frame) override;

private:
  GuestDispatch dispatch_;
  FieldService fieldService_;
  PresentationSync presentationSync_;
};

} // namespace x4::frame
