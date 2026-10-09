// SPDX-License-Identifier: AGPL-3.0-or-later
// sequence_skip_overrides.h - binds the skip to the guest pad route; the rule is in sequence_skip.h.
#pragma once

class Core;

namespace x4::sequence_skip {

void registerOverrides(Core &core);

} // namespace x4::sequence_skip
