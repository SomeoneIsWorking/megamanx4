#include "stream_startup.h"

#include "bios_threads.h"
#include "core.h"

namespace x4::stream_startup {

void awaitField(Core &core) {
  awaitField(core, bios_threads::from(core));
}

void awaitField(Core &, bios_threads::Service &threads) {
  threads.yieldToMain();
}

} // namespace x4::stream_startup
