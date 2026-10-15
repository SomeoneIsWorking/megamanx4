// x4_session.h — Mega Man X4's per-Core state, created with each Game.
#pragma once

#include "bios_threads.h"
#include "fast_wait.h"
#include "game_runtime.h"
#include "movie_cleanup.h"
#include "music_stream.h"
#include "sequence_skip.h"
#include "stage_warp.h"
#include "widened_objects.h"
#include "widescreen_controller.h"

class Core;

namespace psx::cd {
class StockLibcd;
}

namespace x4 {

class X4Session final : public psx::game::TitleSessionState {
public:
  X4Session(Core &core, const psx::cd::StockLibcd &stockLibcd)
      : libcd(stockLibcd), biosThreads(core), movieCleanup(core), musicStream(core), stageWarp(core) {}

  // The runtime's libcd; the title's CD wrappers call its bodies.
  const psx::cd::StockLibcd &libcd;
  bios_threads::Service biosThreads;
  fast_wait::State fastWait;
  movie_cleanup::State movieCleanup;
  music_stream::State musicStream;
  WidescreenController widescreen;
  cull::WidenedObjects widenedObjects;
  sequence_skip::SequenceSkip sequenceSkip;
  StageWarp stageWarp;
};

X4Session &session(Core &core);
const X4Session &session(const Core &core);

// The session libcd's CdSync and CdControl bodies, as guest-body leaves for the CD wrappers.
void stockCdSync(Core *core);
void stockCdControl(Core *core);

} // namespace x4
