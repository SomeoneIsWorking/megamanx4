#pragma once

#include "bios_threads.h"
#include "fast_wait.h"
#include "movie_cleanup.h"
#include "music_stream.h"
#include "widescreen_controller.h"

class Core;

namespace x4 {

struct X4Context {
  explicit X4Context(Core &core) : biosThreads(core), movieCleanup(core), musicStream(core) {}
  X4Context(Core &core, movie_cleanup::SuspendField suspendMovieField)
      : biosThreads(core), movieCleanup(core, suspendMovieField), musicStream(core) {}

  bios_threads::Service biosThreads;
  fast_wait::State fastWait;
  movie_cleanup::State movieCleanup;
  music_stream::State musicStream;
  WidescreenController widescreen;
};

X4Context &context(Core &core);
const X4Context &context(const Core &core);

} // namespace x4
