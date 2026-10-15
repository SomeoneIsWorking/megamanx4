#pragma once

#include "config_var.h"

namespace x4 {

// pc_enh knobs; read them through psx::config::enh so comparison runs suppress them.
psx::config::BoolVar &widescreenCvar(); // PSXPORT_X4_WIDESCREEN
psx::config::BoolVar &coopCvar();       // PSXPORT_X4_COOP
psx::config::BoolVar &fastWaitCvar();   // PSXPORT_X4_FASTWAIT
psx::config::BoolVar &skipCvar();       // PSXPORT_X4_SKIP

// States the declared knobs no feature reads yet.
void reportUnreadEnhancements();

} // namespace x4
