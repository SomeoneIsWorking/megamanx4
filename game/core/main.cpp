// main.cpp — the Mega Man X4 port's process entry point.
//
// Installs X4Runtime, loads the authenticated retail executable, brings up the framework's PSX
// hardware backends, and enters the native/Lightrec runtime.
#include "cfg.h"
#include "command_line.h"
#include "core.h"
#include "dbg_server.h" // debug_server_live + DbgServer::attach — the live control channel
#include "disc.h"
#include "enhancements.h"
#include "fs_util.h"
#include "game.h"
#include "hw_bind.h"
#include "psx_exe_image.h"
#include "store_observe.h" // store_observe_attach — PSXPORT_STORE_OBSERVE on a title-owned spine
#include "vram_rect_queue.h"
#include "x4_runtime.h"
#include <stdio.h>

extern "C" {
void watchdog_init(void);
void mdec_init(void);
void spu_init(void);
}

void native_boot_run(Core *c); // runtime/psx/native_boot.cpp (framework)

// The retail US executable, as it is named on the disc. SYSTEM.CNF boots it directly
// (`BOOT = cdrom:\SLUS_005.61;1` — measured 2026-08-12), so there is no SCEA boot stub LoadExec'ing a
// second image the way Tomba!2's SCUS_944.54 -> MAIN.EXE hand-off does; the framework's stub stage is
// unused here.
static const char *kDiscExePath = "\\SLUS_005.61";

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

  // Process-lifetime derived owner. Installation must precede the first Core, which snapshots it.
  static x4::X4Runtime runtime;
  psxport_install_game(runtime);
  // Say out loud which enhancement knobs this run will do NOTHING with. Co-op and fast-wait remain
  // `planned` (docs/project-goals.md), so a user who sets PSXPORT_X4_COOP=1 today would
  // otherwise see a completely clean startup and a clean exit audit — registering them as CVars is
  // exactly what removed the framework's "UNKNOWN knob ... it did NOTHING" warning for them.
  x4::audit_declared_enhancements();

  const char *path = options.executablePath;

  Game *game = new Game();
  Core *c = &game->core;

  // Self-provision the executable so the binary is runnable straight from a disc image with no prior
  // step (disc resolution: $PSXPORT_X4_DISC, .env, or a *.chd in the working directory — the
  // same order tools/resolve_disc.py implements host-side).
  if (!Fs::exists(path)) {
    cfg_logw("boot", "%s missing — extracting from disc", path);
    if (!disc_extract_file(&game->disc, kDiscExePath, path)) {
      cfg_loge("boot",
               "extraction failed: provide a disc (PSXPORT_X4_DISC, .env, or a *.chd in "
               "the working directory), or run `python3 tools/extract_exe.py`");
      return 1;
    }
  }

  watchdog_init(); // PSXPORT_WATCHDOG=<sec>: abort + backtrace if a frame stalls
  load_exe(path, c);

  gte_init();                  // GTE (COP2)
  mdec_init();                 // MDEC (FMV)
  spu_init();                  // SPU
  game->spu_audio.init();      // SDL audio sink (PSXPORT_NOAUDIO to disable)
  game->gpu.gpu_native_init(); // native GPU renderer over the guest's GP0 stream
  game->cd.overridesInit();    // native CD: drive-ready + by-LBA read
  // Generic hardware-sync entries remain zero. RE-11's game-specific wait producer is installed from
  // registerOverrides below, after initBuiltins has exercised and reported the generic table.
  game->platform_hle.initBuiltins();
  game->pad.overridesInit(); // native controller input
  c->r[4] = 1;
  c->r[5] = 0; // a0/a1 as the BIOS leaves them

  c->runtime->registerOverrides(*game);
  // PSXPORT_DEBUG_SERVER: the live control channel, attached BEFORE the frame loop so a client-driven
  // run is uncapped and a `pause` can be honoured per field. This title had NO live endpoint at all —
  // `grep -rn dbg_server game/` returned nothing — so it could not be driven, observed or captured over
  // the channel, which is the only way this workspace accepts evidence about a running product. The
  // framework's own boot path calls `dbg_server.start` for the same reason; a title-owned spine has to
  // attach it itself, which is what `attach` is for (it also answers the frame cap).
  const int clientFrameCap = game->dbg_server.attach(c, cfg_int("PSXPORT_NATIVE_FRAMES", 0));
  // PSXPORT_STORE_OBSERVE: this is a TITLE-OWNED spine, so it never reaches the framework's
  // `native_boot_run` line that arms the dynarec store observer, and would be silently unarmed while
  // the boot audit printed the variable as `[env]`. Measured on Spyro 1, where `nm -C` showed the
  // symbol linked in and the audit showed the variable set, yet a run with
  // `PSXPORT_STORE_OBSERVE=nothex` printed not one line — not even the parse refusal that a bad token
  // emits unconditionally. Same class of opt-in diagnostic as the live endpoint, same spine.
  store_observe_attach(*c);
  lucent::info("boot",
               "live control channel {} (client frame cap {})",
               debug_server_live() ? "attached" : "not requested",
               clientFrameCap);
  native_boot_run(c);
  // The frame loop has returned, so this is the title's run-end path. The guest-call census lives
  // with the Core that made the calls: it reports how many completed, how many had to be RESUMED
  // past the one-display-field host turn, and the deepest one. (X4Runtime::bootInit is not the run
  // end - native_boot_run calls it to enter the loop.)
  c->guestCallCensus().log("after native boot");
  // The rectangle queue's census names how many appends were REFUSED for want of room, which is
  // the number that says whether the bound this repository added is load-bearing on this disc. A
  // run that never refuses it says so with a denominator rather than by silence.
  x4::vram_rect::reportCensus("after native boot");
  cfg_logi("boot", "native boot returned");
  return 0;
}
