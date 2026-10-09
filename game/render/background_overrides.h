// SPDX-License-Identifier: AGPL-3.0-or-later
// background_overrides.h - binds the background tile layer owners to the native seam; the layout is in
// background_tiles.h.
#pragma once

class Core;

namespace x4::background {

// Wraps the layer draw and the ring refill: the retail body runs first, the wide margin is added after it.
void registerOverrides(Core &core);

} // namespace x4::background
