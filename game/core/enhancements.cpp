// enhancements.cpp — defines this port's three pc_enh CVars and the ONE suppression chokepoint.
//
// See enhancements.h for why the chokepoint exists. See ../../docs/config.md for the knob table and
// ../../docs/behavior-map.md for the divergence ledger (`tools/behavior.py check` is the gate).
#include "enhancements.h"
#include "cfg.h"

namespace x4 {

// ── THE INVENTORY ───────────────────────────────────────────────────────────────────────────────
// On the ladder (runtime/recomp/config_var.h):
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
psx::config::BoolVar cv_widescreen(
    "PSXPORT_X4_WIDESCREEN", false,
    "pc_enh: wider-than-4:3 FOV driven from game state (affect=full; suppressed under ORACLE/SBS)",
    /*persistable=*/true);

psx::config::BoolVar cv_coop(
    "PSXPORT_X4_COOP", false,
    "pc_enh: drop-in second player — P2 spawns as the other hunter (affect=full; suppressed under "
    "ORACLE/SBS)",
    /*persistable=*/true);

psx::config::BoolVar cv_fastwait(
    "PSXPORT_X4_FASTWAIT", false,
    "pc_enh: collapse the game's OWN scripted wait/fade ramps (affect=full; suppressed under "
    "ORACLE/SBS)",
    /*persistable=*/true);

// ── NO CONSUMER YET IS A THING THE RUN MUST SAY ─────────────────────────────────────────────────
// Declaring these as CVars buys the ladder, the settings file and the REPL dump — and it COSTS the one
// runtime signal the framework had for "you set a knob and nothing happened": an unrecognised
// PSXPORT_* name gets `[cfg:warn] UNKNOWN knob ... it did NOTHING in this run` plus an UNKNOWN count in
// the exit audit, while a registered knob with zero call sites resolves silently to `true` and looks
// like a working feature. All three features are `status: planned` (docs/re-frontier.md RE-07/08/09) and
// `grep -rn 'x4::enh' game/` finds no call site outside this file, so today ALL THREE are in this list.
//
// DELETING AN ENTRY IS PART OF THE COMMIT THAT ADDS THE FIRST REAL CALL SITE — that is the whole
// protocol. An entry left here after the feature lands turns a real enhancement into a nag; an entry
// removed early turns a silent no-op back into something that reads as working.
struct Unimplemented {
  psx::config::BoolVar* var;
  const char* step;          // the frontier step that will give it a consumer
};
static const Unimplemented kUnimplemented[] = {
    {&cv_widescreen, "RE-08"},
    {&cv_coop,       "RE-07"},
    {&cv_fastwait,   "RE-09"},
};

static const char* unimplemented_step(const psx::config::BoolVar& v) {
  for (const auto& u : kUnimplemented) {
    if (u.var == &v) return u.step;
  }
  return nullptr;
}

// One-time-per-knob bookkeeping, keyed on the CVar's own identity so a fourth knob needs no edit here.
// Two independent registers: a run can legitimately warn about suppression AND about no-consumer for
// different knobs, and neither may silence the other.
static const void* g_warned_suppressed[8] = {nullptr};
static const void* g_warned_unimpl[8] = {nullptr};

static bool warn_once(const void* key, const void* (&reg)[8]) {
  int free_slot = -1;
  for (int i = 0; i < 8; ++i) {
    if (reg[i] == key) return false;
    if (!reg[i] && free_slot < 0) free_slot = i;
  }
  if (free_slot >= 0) reg[free_slot] = key;
  return true;
}

// ── THE CHOKEPOINT ──────────────────────────────────────────────────────────────────────────────
// The three suppression inputs are EXACTLY the ones runtime/recomp/cfg.cpp's cfg_enh() uses —
// oracle_mode() (i.e. psx::config::cv_oracle), cfg_on("PSXPORT_SBS"), and a non-empty
// PSXPORT_SBS_MODE — so the two mechanisms cannot disagree about what a byte-compare run IS. Diverging
// on that definition would mean an SBS variant this gate does not recognise, i.e. a contaminated
// compare that still looks clean.
//
// HONEST NOTE ON THE DUPLICATION. This reproduces cfg_enh's rule instead of calling it, because
// cfg_enh is ENV-ONLY and off the CVar ladder: it reads lucent::config::text("PSXPORT_ENH") directly
// into a function-local seeded static, so it has no Value (settings-file) layer, no Runtime (REPL)
// layer, and never appears in the CVar registry dump. The USER's ruling is CVars, which cfg_enh cannot
// satisfy. The proper fix is UPSTREAM — migrate PSXPORT_ENH onto the ladder, keeping the suppression as
// an explicit resolve-time hook with its own log line, per the framework's docs/config-migration.md
// "Qualification 2" — and a game repo may not make it. Hand it to the operator; do not paper over it
// here, and do not delete this note when the upstream change lands: delete the duplication instead.
bool enh(psx::config::BoolVar& v) {
  const char* sbs_mode = cfg_str("PSXPORT_SBS_MODE");
  const bool compare_run = psx::config::cv_oracle.get()
                        || cfg_on("PSXPORT_SBS")
                        || (sbs_mode && *sbs_mode);
  if (compare_run) {
    // ONE-TIME PER KNOB, not one global flag: a run with two enhancements set must name BOTH, or the
    // second reads as never having been asked for.
    if (warn_once(&v, g_warned_suppressed)) {
      // The framework's own wording, so the two suppressions are greppable together.
      cfg_logw("cfg", "%s SUPPRESSED: oracle/SBS run must stay enhancement-free", v.name());
    }
    return false;
  }
  const bool on = v.get();
  if (on) {
    if (const char* step = unimplemented_step(v)) {
      if (warn_once(&v, g_warned_unimpl)) {
        cfg_logw("cfg", "%s is DECLARED but NO feature reads it yet (%s) — this run did NOTHING with "
                        "it. Enabling it is not evidence that the enhancement works.",
                 v.name(), step);
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
  for (const auto& u : kUnimplemented) {
    if (u.var->get()) (void)enh(*u.var);
  }
}

}  // namespace x4
