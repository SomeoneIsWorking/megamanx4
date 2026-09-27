// input_path.h — READ-ONLY per-field observer for this title's input path.
//
// WHY IT EXISTS. The frame path splits an input EDGE across five stages, and "the pad does not
// work" names none of them:
//
//   1. endpoint accepted `tap`                       -> Pad::driveTap set repl_on/repl_tap/repl_tap_n
//   2. Pad::serviceFrame resolved the effective mask  -> Pad::buttons
//   3. Pad::fillBuffer built the 4-byte packet        (inside the framework, not observable here)
//   4. Hle::biosPadShouldService() gated the write   -> framework gate over the BIOS InitPAD lifecycle
//   5. the guest's own libpad packet buffer           -> x4::pad::kSlot0Buffer / kSlot1Buffer
//
// The frontier issue 0030 could only read stage 5, from outside, once per presented frame, and
// reported "3 of 3 taps produced NO change in the guest's own libpad packet word". That is
// consistent with a break at 1, 2, 4 or 5, so it names a SYMPTOM and not a defect. This observer
// is called from the same place in x4::vsync::deliverField that calls Pad::serviceFrame, once
// before it and once after it, so each field of an edge is sampled at the resolution the edge
// happens at rather than at a ~100-frame poll.
//
// IT WRITES NOTHING. No guest byte is stored, no host state is changed, and no stage is nudged:
// a measurement that could make the value it reports true is not a measurement. Every host value
// it prints is read through a PUBLIC accessor on the framework type that owns it, so the
// observer cannot disagree with the owner by construction.
//
// It is inert unless the `x4-input-path` Lucent channel is enabled, because lucent::debug does
// not evaluate its arguments when the channel is off.
//
// EVERY VALUE IT PRINTS IS A VALUE, NEVER THE NAME OF ONE. The first version printed
// `vbl={kVblankCounter}` — the counter's ADDRESS — where the field index belonged, and the 2026-09-28
// run reported "the edge fields span the VBlank field counter [2148654160, 2148654160]", which is
// 0x8011DC50 spelled out: a constant that reads like a field index and is a perfectly good-looking
// number. tools/live_play.py now reports the field span and the record carries a value that changes
// from field to field, so a constant here is visible rather than plausible.
#pragma once

class Core;

namespace x4::input_path {

// Called immediately BEFORE `c->game->pad.serviceFrame()` and immediately AFTER it, once per
// delivered display field. `phase` is "pre-service" / "post-service" and names WHICH reading of
// the pad's own countdown state this line carries, because the tap countdown is decremented
// inside serviceFrame and a pre-service sample therefore reports the mask the field WILL use.
void observeField(Core &core, const char *phase);

} // namespace x4::input_path
