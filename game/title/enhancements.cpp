// enhancements.cpp - the pc_enh CVars and the enh() gate.
#include "enhancements.h"
#include "cfg.h"

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

// Knobs with no feature reading them yet.
struct Unimplemented {
  psx::config::BoolVar *var;
  const char *step; // the work item that will consume it
};
const Unimplemented kUnimplemented[] = {
    {&cv_coop, "RE-07"},
};

const char *unimplemented_step(const psx::config::BoolVar &v) {
  for (const auto &u : kUnimplemented) {
    if (u.var == &v) {
      return u.step;
    }
  }
  return nullptr;
}

// One warning per knob per run.
class NoConsumerWarnings {
public:
  bool claim(const void *key) {
    int freeSlot = -1;
    for (std::size_t i = 0; i < std::size(warned_); ++i) {
      if (warned_[i] == key) {
        return false;
      }
      if (warned_[i] == nullptr && freeSlot < 0) {
        freeSlot = static_cast<int>(i);
      }
    }
    if (freeSlot >= 0) {
      warned_[static_cast<std::size_t>(freeSlot)] = key;
    }
    return true;
  }

private:
  static constexpr std::size_t kCapacity = 8;
  const void *warned_[kCapacity] = {nullptr};
};

NoConsumerWarnings g_no_consumer_warnings;

bool enh(psx::config::BoolVar &v) {
  const bool on = psx::config::enh(v);
  if (on) {
    if (const char *step = unimplemented_step(v)) {
      if (g_no_consumer_warnings.claim(&v)) {
        cfg_logw("cfg",
                 "%s is DECLARED but NO feature reads it yet (%s) — this run did NOTHING with "
                 "it. Enabling it is not evidence that the enhancement works.",
                 v.name(),
                 step);
      }
    }
  }
  return on;
}

// Pushes every enabled no-consumer knob through enh() once at bring-up; the value is discarded.
void audit_declared_enhancements() {
  for (const auto &u : kUnimplemented) {
    if (u.var->get()) {
      (void)enh(*u.var);
    }
  }
}

} // namespace x4
