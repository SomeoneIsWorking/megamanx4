// SPDX-License-Identifier: AGPL-3.0-or-later
// cull_overrides.h - binds the SLUS_005.61 cull sites to the native seam; the predicate itself is in visibility_cull.h.
#pragma once

#include "visibility_cull.h"

class Core;

namespace x4::cull {

// Installs each cull site at the address its disassembly gave.
void registerOverrides(Core &core);

} // namespace x4::cull
