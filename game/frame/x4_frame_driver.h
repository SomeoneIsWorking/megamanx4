#pragma once

#include "game_runtime.h"
#include "movie_cleanup.h"
#include "music_stream.h"

#include <cstdint>

class Core;

namespace x4::frame {

namespace music = x4::music_stream;
namespace cleanup = x4::movie_cleanup;

using GuestDispatch = void (*)(Core *, std::uint32_t);
using FieldService = void (*)(Core &);
using PresentationSync = void (*)(Core &);

// Run the finite prefix of retail gameMain 0x80012024; the frame shell then repeats via X4FrameDriver.
void bootPrefix(Core &core, GuestDispatch dispatch);
void bootPrefix(Core &core);

// One iteration of the retail main loop with VSync replaced by the field boundary.
class X4FrameDriver final : public FrameDriver {
public:
  X4FrameDriver(GuestDispatch dispatch,
                FieldService fieldService,
                PresentationSync presentationSync,
                cleanup::State &movieCleanup,
                music::State &musicStream);
  void stepFrame(Core &core, std::uint32_t frame) override;

private:
  GuestDispatch dispatch_;
  FieldService fieldService_;
  PresentationSync presentationSync_;
  cleanup::State *movieCleanup_;
  music::State *musicStream_;
};

} // namespace x4::frame
