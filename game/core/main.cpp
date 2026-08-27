// main.cpp — the Mega Man X4 port's process entry point.
//
// Installs X4Runtime + RecompRegistry, brings up the framework's PSX
// hardware backends, loads the retail executable, and enters the native boot. After the install
// nothing here names anything but framework symbols.
//
// RE-01, RE-02's static bootstrap, and RE-06 are measured (docs/re-frontier.md). The sequence below
// boots the generated resident substrate; RE-11 returns from the finite gameMain prefix, then the
// shared shell drives X4FrameDriver one field at a time while full libetc VSync remains trapped.
#include "cfg.h"
#include "command_line.h"
#include "core.h"
#include "disc.h"
#include "enhancements.h"
#include "fs_util.h"
#include "game.h"
#include "recomp_register.h"
#include "x4_runtime.h"
#include <stdio.h>

extern "C" {
void watchdog_init(void);
void mdec_init(void);
void spu_init(void);
}

void load_exe(const char *path, Core *c); // runtime/recomp/boot.cpp (framework)
void native_boot_run(Core *c);            // runtime/recomp/native_boot.cpp (framework)
void gte_init(void);
int selftest_run(const char *path); // runtime/recomp/selftest.cpp (framework harness)

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
    std::fprintf(stderr, "megamanx4_port: %s\n", options.error);
    x4::cli::printUsage(stderr, argv[0]);
    return 2;
  }

  // Process-lifetime derived owner. Installation must precede the first Core, which snapshots it.
  static x4::X4Runtime runtime;
  psxport_install_game(runtime);
  x4_install_recomp();

  // Say out loud which enhancement knobs this run will do NOTHING with. Co-op and fast-wait remain
  // `planned` (docs/re-frontier.md RE-07/09), so a user who sets PSXPORT_X4_COOP=1 today would
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

  // PSXPORT_SELFTEST=<name>: run the framework's headless selftest harness instead of booting.
  {
    const char *st = cfg_str("PSXPORT_SELFTEST");
    if (st && *st) {
      return selftest_run(path);
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
  native_boot_run(c);
  cfg_logi("boot", "native boot returned");
  return 0;
}
