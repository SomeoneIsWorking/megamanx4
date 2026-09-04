// enhancements.cpp — defines this port's three pc_enh CVars and the ONE suppression chokepoint.
//
// See enhancements.h for why the chokepoint exists. See ../../docs/config.md for the knob table and
// ../../docs/behavior-map.md for the divergence ledger (`tools/behavior.py check` is the gate).
#include "enhancements.h"
#include "cfg.h"

namespace x4 {

// ── THE INVENTORY ───────────────────────────────────────────────────────────────────────────────
// On the ladder (runtime/psx/config_var.h):
//     Default   what this port compiled in
//   < Value     the user's persisted choice (psxport_settings.ini)
//   < Override  a launch argument — the PSXPORT_X4_* environment variable. Never persisted.
//   < Runtime   a REPL / debug-server command. This run only. Never persisted.
//
// persistable = true, deliberately: these are USER PREFERENCES, which is the class the Value layer
// exists for (cf. the framework's cv_fps60, whose Value layer is the `fps60=` line the overlay writes).
// Declaring them as CVars rather than reading them with cfg_on is also what keeps them OUT of the
// environment audit's UNKNOWN list and IN the REPL `cvars` dump.
//
// X4 IS THE FIRST REAL CONSUMER OF pc_enh IN THIS WORKSPACE: `cfg_enh()` has zero call sites anywhere,
// and the two names registered in the framework's docs/config.md are both `planned`. That is a finding,
// not a detail — expect to be the one who discovers what this class needs.
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

// ── NO CONSUMER YET IS A THING THE RUN MUST SAY ─────────────────────────────────────────────────
// Declaring these as CVars buys the ladder, the settings file and the REPL dump — and it COSTS the one
// runtime signal the framework had for "you set a knob and nothing happened": an unrecognised
// PSXPORT_* name gets `[cfg:warn] UNKNOWN knob ... it did NOTHING in this run` plus an UNKNOWN count in
// the exit audit, while a registered knob with zero call sites resolves silently to `true` and looks
// like a working feature. Co-op remains `status: planned` (docs/re-frontier.md RE-07) and has no call
// site outside this file, so it remains in this list. Widescreen left the list with its first real
// consumer; fast-wait left it when the loading-coroutine conversion landed (game/core/fast_wait.cpp).
//
// DELETING AN ENTRY IS PART OF THE COMMIT THAT ADDS THE FIRST REAL CALL SITE — that is the whole
// protocol. An entry left here after the feature lands turns a real enhancement into a nag; an entry
// removed early turns a silent no-op back into something that reads as working.
struct Unimplemented {
  psx::config::BoolVar *var;
  const char *step; // the frontier step that will give it a consumer
};
static const Unimplemented kUnimplemented[] = {
    {&cv_coop, "RE-07"},
};

static const char *unimplemented_step(const psx::config::BoolVar &v) {
  for (const auto &u : kUnimplemented) {
    if (u.var == &v) {
      return u.step;
    }
  }
  return nullptr;
}

// One-time-per-knob bookkeeping for title-local no-consumer warnings. Shared comparison suppression
// is owned and reported by psx::config::enh().
static const void *g_warned_unimpl[8] = {nullptr};

static bool warn_once(const void *key, const void *(&reg)[8]) {
  int free_slot = -1;
  for (int i = 0; i < 8; ++i) {
    if (reg[i] == key) {
      return false;
    }
    if (!reg[i] && free_slot < 0) {
      free_slot = i;
    }
  }
  if (free_slot >= 0) {
    reg[free_slot] = key;
  }
  return true;
}

// ── THE CHOKEPOINT ──────────────────────────────────────────────────────────────────────────────
// Selection and comparison-run suppression have one shared owner. This title wrapper adds only its
// no-consumer audit; duplicating the diagnostic-role rule here would let the two definitions drift.
bool enh(psx::config::BoolVar &v) {
  const bool on = psx::config::enh(v);
  if (on) {
    if (const char *step = unimplemented_step(v)) {
      if (warn_once(&v, g_warned_unimpl)) {
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

// ── THE STARTUP AUDIT ───────────────────────────────────────────────────────────────────────────
// The read-time warning above is necessary but NOT sufficient, and the difference is the whole point:
// a knob with no consumer is never READ, so a warning that only fires inside enh() is a warning that
// can never print for exactly the knobs it is about. This runs once at bring-up (main.cpp, right after
// the seam install) and pushes every knob the user asked for THROUGH the chokepoint, so the run says
// either "SUPPRESSED" (compare run) or "DECLARED but NO feature reads it yet". The value is discarded:
// this is an announcement, not a read.
//
// It walks kUnimplemented, not all three CVars, so it goes quiet on its own as features land.
void audit_declared_enhancements() {
  for (const auto &u : kUnimplemented) {
    if (u.var->get()) {
      (void)enh(*u.var);
    }
  }
}

} // namespace x4
