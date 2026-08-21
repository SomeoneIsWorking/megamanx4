// recomp_register.cpp — fills the framework↔generated-substrate seam (recomp_iface.h) from THIS
// game's recompiled symbols. This is the ONE file that names generated/ symbols; the framework
// reaches them only through psxport_recomp()->field.
//
// RE-02's retail-binary bootstrap measurement proves the generated resident interface: main_dispatch,
// rec_func_index, shard_set_override, and an empty g_rec_overlays table.  This adapter names exactly
// those measured symbols.  The seam target still compiles the no-substrate branch so a clean clone does
// not need generated code merely to run the first-party C++ policy gate.
#include "cfg.h"
#include "core.h"
#include "recomp_iface.h"
#include <stdlib.h>

#ifdef MMX4_HAVE_SUBSTRATE
#include "overlay_table.h"

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
