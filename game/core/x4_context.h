#pragma once

#include "bios_threads.h"
#include "fast_wait.h"
#include "widescreen_controller.h"

class Core;

namespace x4 {

struct X4Context {
  explicit X4Context(Core &core) : biosThreads(core) {}

  bios_threads::Service biosThreads;
  fast_wait::State fastWait;
  WidescreenController widescreen;
};

X4Context &context(Core &core);

} // namespace x4
