---
id: 1
title: psxport_smoke cannot be built from a consumer tree (framework defect)
status: open
symptom: cmake -DPSXPORT_BUILD_SMOKE=ON in a game repo fails: 'Cannot find source file: tools/smoke/psxport_smoke.cpp' / 'No SOURCES given to target: psxport_smoke'
tags: framework,build,agnosticism
created: 2026-08-12
updated: 2026-08-12
---

CARRIED FORWARD from vagrant/docs/issues/0001, deliberately: a fresh tree that omits it makes the next session re-derive what has already been paid for. That is the point of a catalogue. NOT re-measured here (this repo has never configured with -DPSXPORT_BUILD_SMOKE=ON), and the framework line it names is unchanged at the pin this tree records.

CAUSE: external/psxport/cmake/psxport.cmake:237 is `add_executable(psxport_smoke tools/smoke/psxport_smoke.cpp)` — a RELATIVE source path. CMake resolves it against CMAKE_CURRENT_SOURCE_DIR, which for an `include()`d framework fragment is the CONSUMING game repo, not the framework. Every other framework path in that file already goes through ${PSXPORT_ROOT} (defined from CMAKE_CURRENT_LIST_DIR); this one line does not.

CONSEQUENCE: the psxport_smoke link — the framework's stated proof that no game symbol is required — is only runnable from inside the psxport repo. A game repo cannot re-check agnosticism against the framework revision it actually builds. Affects spyro, spider1, Tomba2Engine and vagrant identically.

FIX (one line, upstream, NOT made here — a game repo may not edit the framework):
  add_executable(psxport_smoke ${PSXPORT_ROOT}/tools/smoke/psxport_smoke.cpp)

WORKAROUND used here: none. -DPSXPORT_BUILD_SMOKE stays OFF (the default) and this repo's gate is the megamanx4_seam OBJECT library, which compiles the seam TUs — including enhancements.cpp — against the pinned framework headers.
