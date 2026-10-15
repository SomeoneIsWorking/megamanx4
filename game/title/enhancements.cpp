#include "enhancements.h"

#include <lucent/log.h>

namespace x4 {

// User preferences, so they persist in the settings file.
namespace {

psx::config::BoolVar
    cv_widescreen("PSXPORT_X4_WIDESCREEN",
                  true,
                  "pc_enh: wider-than-4:3 FOV driven from game state (affect=full; suppressed in comparison runs)",
                  /*persistable=*/true);

psx::config::BoolVar
    cv_coop("PSXPORT_X4_COOP",
            false,
            "pc_enh: drop-in second player — P2 spawns as the other hunter (affect=full; suppressed in "
            "comparison runs)",
            /*persistable=*/true);

psx::config::BoolVar cv_fastwait("PSXPORT_X4_FASTWAIT",
                                 true,
                                 "pc_enh: convert the retail loading coroutine into one synchronous call — the wait "
                                 "bodies still run byte-exactly, but no loading frame is ever presented (affect=full; "
                                 "suppressed in comparison runs)",
                                 /*persistable=*/true);

psx::config::BoolVar
    cv_skip("PSXPORT_X4_SKIP",
            true,
            "pc_enh: holding Start skips the Hunter H.Q. briefing by raising the game's own page-advance "
            "input (affect=full; suppressed in comparison runs)",
            /*persistable=*/true);

} // namespace

psx::config::BoolVar &widescreenCvar() {
  return cv_widescreen;
}

psx::config::BoolVar &coopCvar() {
  return cv_coop;
}

psx::config::BoolVar &fastWaitCvar() {
  return cv_fastwait;
}

psx::config::BoolVar &skipCvar() {
  return cv_skip;
}

// Co-op is declared for the settings file; its feature (RE-07) does not exist yet.
void reportUnreadEnhancements() {
  lucent::info("x4-enh", "{}={} is declared but no feature reads it yet (RE-07)", cv_coop.name(), cv_coop.get());
}

} // namespace x4
