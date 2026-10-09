// SPDX-License-Identifier: AGPL-3.0-or-later
// sequence_skip.h - Start skips a non-interactive sequence by feeding the game its own advance input.
// The Hunter H.Q. briefing (engine state 3, sub-state 9) shows its pages until the player presses Cross; while
// Start is held the Cross edge is raised on a fixed field cadence, so the retail owner runs every page to the end.
#pragma once

#include <cstdint>

class Core;

namespace x4::sequence_skip {

// engine_obj: byte +0 state, byte +1 sub-state, byte +2 the sub-state's own step.
inline constexpr std::uint32_t kEngineAddress = 0x801721C0u;
inline constexpr std::uint32_t kEngineStateOffset = 0x00u;
inline constexpr std::uint32_t kEngineSubStateOffset = 0x01u;
// State 3 hosts the movie, loading and briefing sub-states; sub-state 9 is the briefing room (0x8002F4C4).
inline constexpr std::uint8_t kBriefingState = 3;
inline constexpr std::uint8_t kBriefingSubState = 9;

// Guest button words (`~packet`, bytes 2-3 of the libpad record): Start is bit 3 of byte 2, Cross bit 6 of byte 3.
inline constexpr std::uint16_t kStartMask = 0x0800u;
inline constexpr std::uint16_t kCrossMask = 0x0040u;

// A page finishes typing and then waits for the edge, so a held Cross would not advance; one edge per cadence does.
inline constexpr std::uint32_t kAdvanceCadence = 4;

class SequenceSkip {
public:
  static bool inBriefing(Core &core);

  // Runs after the retail pad route of every field and rewrites its Cross held/edge words while skipping.
  void afterPadRoute(Core &core);

  std::uint32_t fieldsSkipped() const {
    return fields_;
  }

private:
  std::uint32_t fields_ = 0;
};

} // namespace x4::sequence_skip
