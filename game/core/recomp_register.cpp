// recomp_register.cpp — fills the framework↔generated-substrate seam (recomp_iface.h) from THIS
// game's recompiled symbols. This is the ONE file that names generated/ symbols; the framework
// reaches them only through psxport_recomp()->field.
//
// RE-02's retail-binary bootstrap measurement proves the generated resident interface: main_dispatch,
// rec_func_index, shard_set_override, and an empty g_rec_overlays table.  This adapter names exactly
// those measured symbols.  The seam target still compiles the no-substrate branch so a clean clone does
// not need generated code merely to run the first-party C++ policy gate.
#include "recomp_register.h"
#include "cfg.h"
#include "core.h"
#include "fast_wait.h"
#include "recomp_iface.h"
#include "stream_interrupt.h"
#include <stdlib.h>

#ifdef MMX4_HAVE_SUBSTRATE
#include "overlay_table.h"
#include "override_registry.h"
#include "rec_decls.h"
#include "x4_context.h"

// Generated in shard_disp.c with this exact signature.
extern void shard_set_override(uint32_t, void (*)(Core *));

static const RecompRegistry g_x4_recomp = {
    /* main_dispatch        */ main_dispatch,
    /* rec_func_index       */ rec_func_index,
    /* overlays             */ g_rec_overlays,
    /* overlay_count        */ g_rec_overlay_count,
    /* shard_set_override   */ shard_set_override,
    /* ov_a00_set_override  */ nullptr,
    /* ov_game_set_override */ nullptr,
    // No X4 guest-memset override has been measured; execute the generated guest body.
    /* guestMemset_gen      */ nullptr,
};

namespace {

constexpr uint32_t kSetGeomOffset = 0x800E90C8u;
constexpr uint32_t kSetDefDrawEnv = 0x800E9354u;

void publish_projection(Core *core) {
  x4::context(*core).widescreen.publishProjection(*core, gen_func_800E90C8);
}

void publish_draw_environment(Core *core) {
  x4::context(*core).widescreen.publishDrawEnvironment(*core, gen_func_800E9354);
}

void run_direct_request(Core *core) {
  x4::fast_wait::load_synchronously(core,
                                    gen_func_80013890,
                                    gen_func_80013A20,
                                    nullptr,
                                    x4::fast_wait::kDirectReadyCallback,
                                    "direct CD request 0x80013890");
}

void run_direct_cd_setup(Core *core) {
  x4::fast_wait::direct_cd_setup(core, gen_func_80013968, func_800E61BC, func_800E5D40, func_800E5D90, func_80013650);
}

void run_archive_request(Core *core) {
  x4::fast_wait::load_synchronously(core,
                                    gen_func_80013AD8,
                                    gen_func_80013E68,
                                    gen_func_80014780,
                                    x4::fast_wait::kArchiveReadyCallback,
                                    "archive CD request 0x80013AD8");
}

void run_archive_cd_setup(Core *core) {
  x4::fast_wait::archive_cd_setup(core, gen_func_80013DA8, func_800E61BC, func_8001385C, func_800E5D40, func_800E5D90);
}

void remove_loading_presentation_wait(Core *core) {
  x4::fast_wait::loading_presentation_wait(core, gen_func_80013530);
}

void synchronous_cd_ready(Core *core) {
  if (x4::stream_interrupt::consumeCompletedCallback(*core)) {
    return;
  }
  x4::fast_wait::cd_ready(core, gen_func_800E5D40);
}

void synchronous_cd_control(Core *core) {
  x4::fast_wait::cd_control(core, gen_func_800E5D90, false);
}

void synchronous_cd_control_blocking(Core *core) {
  x4::fast_wait::cd_control(core, gen_func_800E5FF4, true);
}

void synchronous_cd_get_sector(Core *core) {
  x4::fast_wait::cd_get_sector(core, gen_func_800E6158);
}

} // namespace
#endif

void x4_install_recomp() {
#ifdef MMX4_HAVE_SUBSTRATE
  psxport_install_recomp(&g_x4_recomp);
#else
  // No substrate: install nothing. NOT silent — a run that gets here has no recompiled code to
  // dispatch to, and finding that out at the first rec_dispatch would blame the wrong thing.
  cfg_loge("recomp",
           "no recompiled substrate is registered: generated/rec_sources.cmake is absent. "
           "Run tools/verify_recomp_bootstrap.py for the measured static-emission gate; "
           "nothing can execute until generated/ is emitted. Refusing to continue.");
  abort();
#endif
}

void x4_install_projection_overrides() {
#ifdef MMX4_HAVE_SUBSTRATE
  engine_set_override_main(kSetGeomOffset, publish_projection, gen_func_800E90C8);
  engine_set_override_main(kSetDefDrawEnv, publish_draw_environment, gen_func_800E9354);
#endif
}

void x4_install_loading_overrides() {
#ifdef MMX4_HAVE_SUBSTRATE
  engine_set_override_main(x4::fast_wait::kDirectRequest, run_direct_request, gen_func_80013890);
  engine_set_override_main(x4::fast_wait::kDirectCdSetup, run_direct_cd_setup, gen_func_80013968);
  engine_set_override_main(x4::fast_wait::kArchiveRequest, run_archive_request, gen_func_80013AD8);
  engine_set_override_main(x4::fast_wait::kArchiveCdSetup, run_archive_cd_setup, gen_func_80013DA8);
  engine_set_override_main(
      x4::fast_wait::kLoadingPresentationWait, remove_loading_presentation_wait, gen_func_80013530);
  engine_set_override_main(x4::fast_wait::kCdReady, synchronous_cd_ready, gen_func_800E5D40);
  engine_set_override_main(x4::fast_wait::kCdControl, synchronous_cd_control, gen_func_800E5D90);
  engine_set_override_main(x4::fast_wait::kCdControlBlocking, synchronous_cd_control_blocking, gen_func_800E5FF4);
  engine_set_override_main(x4::fast_wait::kCdGetSector, synchronous_cd_get_sector, gen_func_800E6158);
#endif
}
