#pragma once

#include "guest_execution.h"

#include "bios_threads.h"
#include "game_runtime.h"
#include "movie_cleanup.h"
#include "music_stream.h"
#include "stage_warp.h"

#include <cstdint>

class Core;

namespace x4::frame {

namespace music = x4::music_stream;
namespace cleanup = x4::movie_cleanup;

using FieldService = void (*)(Core &);
using PresentationSync = void (*)(Core &);

// The host's field delivery and the title's presentation sync, both run once per frame.
struct FieldServices {
  FieldService deliverField;
  PresentationSync synchronizePresentation;
};

// Run the finite prefix of retail gameMain 0x80012024; the frame shell then repeats via X4FrameDriver.
void bootPrefix(Core &core, guest::Dispatch dispatch);
void bootPrefix(Core &core);

// One iteration of the retail main loop with VSync replaced by the field boundary.
class X4FrameDriver final : public psx::game::FrameDriver {
public:
  X4FrameDriver(guest::Dispatch dispatch,
                const FieldServices &fields,
                cleanup::State &movieCleanup,
                music::State &musicStream,
                bios_threads::Service &tasks,
                StageWarp &stageWarp);
  void stepFrame(Core &core, std::uint32_t frame) override;

private:
  guest::Dispatch dispatch_;
  FieldService fieldService_;
  PresentationSync presentationSync_;
  cleanup::State *movieCleanup_;
  music::State *musicStream_;
  bios_threads::Service *tasks_;
  StageWarp *stageWarp_;
};

} // namespace x4::frame
