// Read-only per-field observer of the input path: pad tap -> Pad::buttons -> packet -> guest libpad buffer.
#pragma once

class Core;

namespace x4::input_path {

// Called before and after `serviceFrame` each field; the tap countdown moves inside it.
void observeField(Core &core, const char *phase);

} // namespace x4::input_path
