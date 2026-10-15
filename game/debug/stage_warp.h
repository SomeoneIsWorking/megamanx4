// stage_warp.h — the control-channel `warp <stage> [part]` request.
#pragma once

#include "game_runtime.h"

#include <array>
#include <cstdint>
#include <string>

class Core;

namespace x4 {

// Enters a stage the way the retail part-2 transition (FUN_800200D4) does: stage and part written, then
// engine state 4, whose loader FUN_80013014 reads both. Armed between frames, applied at the next frame
// boundary, and legal only while a stage is running.
class StageWarp final : public psx::game::TitleDevWarp {
public:
  // engine_obj: +0 state, +1 sub-state, +2 step, +0xC stage, +0xD part, +0xF stage-end cause,
  // +0x1E checkpoint marker.
  static constexpr std::uint32_t kEngine = 0x801721C0u;
  static constexpr std::uint32_t kStateOffset = 0x00u;
  static constexpr std::uint32_t kSubStateOffset = 0x01u;
  static constexpr std::uint32_t kStepOffset = 0x02u;
  static constexpr std::uint32_t kStageOffset = 0x0Cu;
  static constexpr std::uint32_t kPartOffset = 0x0Du;
  static constexpr std::uint32_t kStageEndOffset = 0x0Fu;
  static constexpr std::uint32_t kCheckpointMarkerOffset = 0x1Eu;
  static constexpr std::uint8_t kLoadStage = 4;
  static constexpr std::uint8_t kInStage = 6;
  static constexpr std::uint8_t kPlaying = 0; // engine state 6 sub-state 0, FUN_8001FF8C
  static constexpr std::uint32_t kPartCount = 2;
  // Stage ids 0..12; names from the MegaManX4Practice stage constants (docs/prior-art.md).
  static constexpr std::array<const char *, 13> kStageNames{"Intro",
                                                            "Web Spider",
                                                            "Frost Walrus",
                                                            "Split Mushroom",
                                                            "Magma Dragoon",
                                                            "Jet Stingray",
                                                            "Cyber Peacock",
                                                            "Storm Owl",
                                                            "Slash Beast",
                                                            "Colonel",
                                                            "Space Port",
                                                            "Final Weapon 1",
                                                            "Final Weapon 2"};

  explicit StageWarp(Core &core) : core_(core) {}

  int areaCount() const override {
    return static_cast<int>(kStageNames.size());
  }
  const char *areaName(int area) const override;
  bool warpAllowed() const override {
    return stageRunning(core_);
  }

  static bool stageRunning(Core &core);
  // Parses and arms one command line; the returned text answers the client.
  std::string arm(const char *line);
  // Writes the armed request; the frame driver calls it only at a clean frame boundary.
  void applyArmed(std::uint32_t frame);

private:
  Core &core_;
  bool armed_ = false;
  std::uint32_t stage_ = 0;
  std::uint32_t part_ = 0;
};

} // namespace x4
