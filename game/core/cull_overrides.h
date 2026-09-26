// SPDX-License-Identifier: AGPL-3.0-or-later
// cull_overrides.h — the seven measured SLUS_005.61 cull sites, bound to the native seam.
//
// The PREDICATE lives in visibility_cull.h and has no idea a guest exists; this file is the only place
// that knows a guest ABI. Keeping them apart is not tidiness: it is what lets the predicate be tested
// exhaustively over all 65,536 coordinates without linking the guest dispatcher, and it means a change to
// the dispatch seam cannot reach the arithmetic.
//
// Every address and every register this file names was measured from the extracted executable and is
// re-derived by tools/verify_cull.py, which fails the gate if the image disagrees with any of it.
#pragma once

#include "visibility_cull.h"

class Core;

namespace x4::cull {

// Install the measured cull owners against the authenticated SLUS_005.61 image. Each install names the
// address its own disassembly measured, so a registry that disagrees with the binary is visible.
void registerOverrides(Core &core);

} // namespace x4::cull
