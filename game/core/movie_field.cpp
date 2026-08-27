#include "movie_field.h"

#include "bios_threads.h"
#include "core.h"
#include "override_registry.h"

#include <array>
#include <cstdlib>
#include <lucent/log.h>

#ifdef MMX4_HAVE_SUBSTRATE
extern void gen_func_80018000(Core *);
extern void gen_func_800182E8(Core *);
extern void gen_func_80018B88(Core *);
extern void shard_set_override(std::uint32_t, void (*)(Core *));
#endif

namespace x4::movie {
namespace {

constexpr std::array<std::uint32_t, 4> kFieldReturnAddresses = {
    0x8001810Cu,
    0x8001842Cu,
    0x800185D8u,
    0x80018BC4u,
};

bool isFieldReturnAddress(std::uint32_t address) {
  for (const std::uint32_t expected : kFieldReturnAddresses) {
    if (address == expected) {
      return true;
    }
  }
  return false;
}

#ifdef MMX4_HAVE_SUBSTRATE
void runGeneral(Core *core) {
  x4_native_general_movie(core);
}

void runCapcom(Core *core) {
  x4_native_capcom_movie(core);
}

void runFrame(Core *core) {
  x4_native_movie_frame(core);
}
#endif

} // namespace

void yieldField(Core *core, std::uint32_t returnAddress) {
  if (!core) {
    lucent::error("x4-movie", "native movie field boundary received a null Core at 0x{:08X}", returnAddress);
    std::abort();
  }
  yieldField(*core, returnAddress, bios_threads::from(*core));
}

void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads) {
  if (core.r[31] != returnAddress || !isFieldReturnAddress(returnAddress)) {
    lucent::error("x4-movie",
                  "unauthenticated native movie field boundary argument=0x{:08X} ra=0x{:08X}",
                  returnAddress,
                  core.r[31]);
    std::abort();
  }

  // VSync(0)'s return is not consumed at these three call sites. Park the existing retail task
  // stack until X4FrameDriver begins the next host-owned field, then preserve a deterministic zero
  // in v0 without ever entering libetc VSync.
  threads.yieldToMain();
  core.r[2] = 0u;
}

void registerOverrides() {
#ifdef MMX4_HAVE_SUBSTRATE
  overrides::install(kGeneralMovie, "movie::general", runGeneral, gen_func_80018000, shard_set_override);
  overrides::install(kCapcomMovie, "movie::capcom", runCapcom, gen_func_800182E8, shard_set_override);
  overrides::install(kMovieFrame, "movie::frame", runFrame, gen_func_80018B88, shard_set_override);
#else
  lucent::debug("x4-movie", "movie field registration deferred: no generated substrate");
#endif
}

} // namespace x4::movie
