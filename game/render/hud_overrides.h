// SPDX-License-Identifier: AGPL-3.0-or-later
// hud_overrides.h - binds the HUD pass to the native seam; the packet shifting is in hud_anchor.h.
#pragma once

class Core;

namespace x4::hud {

void registerOverrides(Core &core);

} // namespace x4::hud
