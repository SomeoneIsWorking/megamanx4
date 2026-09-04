#ifndef MMX4_ENHANCEMENTS_H
#define MMX4_ENHANCEMENTS_H
// enhancements.h — THE THREE pc_enh GATES OF THIS PORT, and the ONE chokepoint they all pass through.
//
// This file has no counterpart in any other tree in the workspace, because no other tree is an
// ENHANCEMENT port. Mega Man X4 needs no native producer, no frame interpolation and no native depth
// (it already runs at 60fps — USER decision 2026-08-12, quoted verbatim in ../../CLAUDE.md); what it
// needs is three deliberate changes to what the GAME DOES. In the framework's behaviour taxonomy all
// three are:
//
//     class:  pc_enh
//     affect: full     — they DELIBERATELY change canon guest state
//
// `affect: full` is the only class that MUST be force-suppressed under a byte-compare run, and
// docs/behavior-map.md's `check` gate FAILS an `affect: full` entry whose `guard` does not cite that
// suppression. Registered knobs: ../../docs/config.md. Design: ../../docs/plans/enhancements.md.
//
// WHY A CHOKEPOINT AND NOT A CVar READ AT EACH CALL SITE. The framework put cfg_enh()'s suppression in
// cfg.cpp for a stated reason — "that suppression is the whole point of this function living in cfg
// rather than at each call site". Same reason here: EVERY read goes through x4::enh(), which delegates
// to the shared typed diagnostic-role gate.
// Calling `.get()` at a feature call site is the bug this header exists to prevent.
#include "config_var.h"  // psx::config::BoolVar
#include "config_vars.h" // psx::config::enh — shared selection and comparison suppression

namespace x4 {

extern psx::config::BoolVar cv_widescreen; // PSXPORT_X4_WIDESCREEN
extern psx::config::BoolVar cv_coop;       // PSXPORT_X4_COOP
extern psx::config::BoolVar cv_fastwait;   // PSXPORT_X4_FASTWAIT

// Delegates selection and typed comparison-run suppression to psx::config::enh(), then reports a
// title-local no-consumer warning where applicable.
bool enh(psx::config::BoolVar &v);

// Call ONCE at bring-up (main.cpp). Announces every knob the user turned on that no feature reads yet
// — the case enh() cannot report, because a knob with no consumer is never read. A registered CVar with
// zero call sites otherwise resolves silently to `true`, and the framework's `[cfg:warn] UNKNOWN knob
// ... it did NOTHING in this run` only fires for names it does NOT know, so registering these knobs
// removed the one signal that would have said so. This puts it back until each feature lands.
void audit_declared_enhancements();

} // namespace x4

#endif // MMX4_ENHANCEMENTS_H
