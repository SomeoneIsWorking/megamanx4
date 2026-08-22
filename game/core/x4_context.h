#pragma once

#include "bios_threads.h"

class Core;

namespace x4 {

struct X4Context {
  explicit X4Context(Core &core) : biosThreads(core) {}

  bios_threads::Service biosThreads;
};

X4Context &context(Core &core);

} // namespace x4
