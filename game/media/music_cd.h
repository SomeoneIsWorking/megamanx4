// music_cd.h -- native ownership of the XA/BGM state machine's stock libcd leaf calls.
#pragma once

#include <array>
#include <cstdint>

class Core;

namespace x4::music_cd {

using GuestBody = void (*)(Core *);

// Handlers on the 6 -> 5 -> 1 chain open with CdSync (0x800E5D20) and park unless v0 is CdlComplete;
// CD_sync would poll a controller this port lacks, so the framework CD owner answers instead. State 7
// belongs to x4::music_stream.
inline constexpr std::uint32_t kCdSyncEntry = 0x800E5D20u;
inline constexpr std::uint32_t kStepTable = 0x800F1AB0u;

// D_80141BD4 must be 2 for the machine to run; D_80139530 is the state, D_8013952C the sticky error byte.
// 0x80139554 is the CdControl result buffer that func_80016B58 tests for shell-open bit 0x40.
inline constexpr std::uint32_t kMusicActive = 0x80141BD4u;
inline constexpr std::uint32_t kMachineState = 0x80139530u;
inline constexpr std::uint32_t kError = 0x8013952Cu;
inline constexpr std::uint32_t kResult = 0x80139554u;

// One step: handler state, plus the jal address and return address (jal + 8) of each leaf call.
// parameter and result are the a1/a2 literals the handler loads.
struct Step {
  std::uint32_t state;
  std::uint32_t handler;
  std::uint32_t syncCall;
  std::uint32_t syncReturn;
  std::uint32_t commandCall;
  std::uint32_t commandReturn;
  std::uint32_t command;
  std::uint32_t parameter;
  std::uint32_t result;
};

// What a `jal` leaves in r[31]: its own address plus 8, skipping its own delay slot.
inline constexpr std::uint32_t kJalReturnOffset = 8u;

// 6 CdlSetfilter -> machine state 5; 5 CdlSeekL -> 1; 1 CdlReadS -> handshake byte (Psy-Q LIBCD.H ids).
inline constexpr std::uint32_t kCommandComplete = 2u;
inline constexpr std::uint32_t kShellOpenBit = 0x40u;
inline constexpr std::uint32_t kCommandEntry = 0x800E5D90u;

// 0x80016BA4 is spelled as jal + offset to show where its return 0x80016BAC comes from.
inline constexpr std::array<Step, 3> kSteps{
    Step{6u, 0x80016E34u, 0x80016E40u, 0x80016E48u, 0x80016E5Cu, 0x80016E64u, 0x0Du, 0x80175EE8u, 0u},
    Step{5u, 0x80016DACu, 0x80016DB8u, 0x80016DC0u, 0x80016DE8u, 0x80016DF0u, 0x15u, 0x80139514u, 0u},
    Step{
        1u, 0x80016B58u, 0x80016B74u, 0x80016B7Cu, 0x80016BA4u, 0x80016BA4u + kJalReturnOffset, 0x1Bu, 0u, 0x80139554u},
};
inline constexpr std::uint32_t kStepCount = static_cast<std::uint32_t>(kSteps.size());

// A return address that is not jal + 8 never matches, silently.
[[nodiscard]] constexpr bool everyReturnIsItsJalPlusTheDelaySlot() noexcept {
  for (const Step &step : kSteps) {
    if (step.syncReturn != step.syncCall + kJalReturnOffset ||
        step.commandReturn != step.commandCall + kJalReturnOffset) {
      return false;
    }
  }
  return true;
}
static_assert(kSteps[0].syncReturn == kSteps[0].syncCall + kJalReturnOffset);
static_assert(kSteps[0].commandReturn == kSteps[0].commandCall + kJalReturnOffset);
static_assert(kSteps[1].syncReturn == kSteps[1].syncCall + kJalReturnOffset);
static_assert(kSteps[1].commandReturn == kSteps[1].commandCall + kJalReturnOffset);
static_assert(kSteps[2].syncReturn == kSteps[2].syncCall + kJalReturnOffset);
static_assert(kSteps[2].commandReturn == kSteps[2].commandCall + kJalReturnOffset);
static_assert(everyReturnIsItsJalPlusTheDelaySlot(),
              "a Step's return address must be its own jal plus the delay slot, or the owner will "
              "never match that edge and the call silently falls through to a policy this port "
              "cannot complete");

// Named steps of the 6 -> 5 -> 1 chain.
inline constexpr const Step &kSetFilterStep = kSteps[0];
inline constexpr const Step &kSeekStep = kSteps[1];
inline constexpr const Step &kReadStep = kSteps[2];

const Step *stepForSyncReturn(std::uint32_t returnAddress) noexcept;
const Step *stepForCommandReturn(std::uint32_t returnAddress) noexcept;

// Return false (existing policy stays) when r[31] is not one of the edges above.
bool serveCdSync(Core *core, GuestBody stockSync, GuestBody originalSync);
bool serveCdControl(Core *core, GuestBody stockControl);

// Image-scoped owner of the stock libcd CdSync leaf. Unmeasured callers keep the original body.
void registerOverrides(Core &core);

} // namespace x4::music_cd
