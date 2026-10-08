// Process entry: install the runtime, load the executable, bring up hardware, run.
#include "bios_threads.h" // Service::reportCensus — the retail task-turn census
#include "c_subsys.h"     // watchdog_init / mdec_init — the C-linkage subsystem leaves
#include "cfg.h"
#include "command_line.h"
#include "core.h"
#include "dbg_server.h" // debug_server_live + DbgServer::attach — the live control channel
#include "disc.h"
#include "enhancements.h"
#include "fs_util.h"
#include "game.h"
#include "hw_bind.h"     // gte_init / spu_init
#include "native_boot.h" // native_boot_run
#include "psx_exe_image.h"
#include "store_observe.h" // store_observe_attach — PSXPORT_STORE_OBSERVE on a title-owned spine
#include "vram_rect_queue.h"
#include "x4_runtime.h"
#include <stdio.h>

namespace {

// SYSTEM.CNF boots the executable directly.
constexpr const char *kDiscExePath = "\\SLUS_005.61";

// Constructed before main(); Core snapshots it at construction.
x4::X4Runtime g_runtime;

} // namespace

int main(int argc, char **argv) {
  const x4::cli::Options options = x4::cli::parse(argc, argv);
  if (options.action == x4::cli::Action::Help) {
    x4::cli::printUsage(stdout, argv[0]);
    return 0;
  }
  if (options.action == x4::cli::Action::Error) {
    cfg_loge("cli", "megamanx4_port: %s", options.error);
    x4::cli::printUsage(stdout, argv[0]);
    return 2;
  }

  psxport_install_game(g_runtime);

  x4::audit_declared_enhancements();

  const char *path = options.executablePath;

  Game *game = new Game();
  Core *c = &game->core;

  // Provision the executable from the disc.
  if (!Fs::exists(path)) {
    cfg_logw("boot", "%s missing — extracting from disc", path);
    if (!disc_extract_file(&game->disc, kDiscExePath, path)) {
      cfg_loge("boot",
               "extraction failed: provide a disc (PSXPORT_X4_DISC, .env, or a *.chd in "
               "the working directory), or run `python3 tools/extract_exe.py`");
      return 1;
    }
  }

  watchdog_init(); // PSXPORT_WATCHDOG=<sec>: abort + backtrace on a stalled frame
  load_exe(path, c);

  gte_init();                  // GTE (COP2)
  mdec_init();                 // MDEC (FMV)
  spu_init();                  // SPU
  game->spu_audio.init();      // SDL audio sink (PSXPORT_NOAUDIO to disable)
  game->gpu.gpu_native_init(); // native renderer over the guest's GP0 stream
  game->cd.overridesInit();    // native CD: drive-ready + by-LBA read
  // Hardware-sync entries stay zero; the title installs its wait producer in registerOverrides.
  game->platform_hle.initBuiltins();
  game->pad.overridesInit(); // native controller input
  c->r[4] = 1;
  c->r[5] = 0; // a0/a1 as the BIOS leaves them

  c->runtime->registerOverrides(*game);
  // Attach before the frame loop so a client-driven run is uncapped and `pause` works.
  const int clientFrameCap = game->dbg_server.attach(c, cfg_int("PSXPORT_NATIVE_FRAMES", 0));
  // This spine bypasses the line in `native_boot_run` that arms the store observer.
  store_observe_attach(*c);
  lucent::info("boot",
               "live control channel {} (client frame cap {})",
               debug_server_live() ? "attached" : "not requested",
               clientFrameCap);
  native_boot_run(c);
  c->guestCallCensus().log("after native boot");
  x4::vram_rect::reportCensus("after native boot");
  x4::bios_threads::from(*c).reportCensus("after native boot");
  cfg_logi("boot", "native boot returned");
  return 0;
}
