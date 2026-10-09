#ifndef MMX4_ENHANCEMENTS_H
#define MMX4_ENHANCEMENTS_H
// A feature must call x4::enh(), never `.get()`, so comparison-run suppression applies.
#include "config_var.h"  // psx::config::BoolVar
#include "config_vars.h" // psx::config::enh — shared selection and comparison suppression

namespace x4 {

// Singletons owned by enhancements.cpp.
psx::config::BoolVar &widescreenCvar(); // PSXPORT_X4_WIDESCREEN
psx::config::BoolVar &coopCvar();       // PSXPORT_X4_COOP
psx::config::BoolVar &fastWaitCvar();   // PSXPORT_X4_FASTWAIT
psx::config::BoolVar &skipCvar();       // PSXPORT_X4_SKIP

// Delegates to psx::config::enh() and warns once if the knob has no consumer yet.
bool enh(psx::config::BoolVar &v);

// Announce enabled knobs that nothing reads, which enh() never sees.
void audit_declared_enhancements();

} // namespace x4

#endif // MMX4_ENHANCEMENTS_H
