// music_cd.h -- native ownership of the XA/BGM state machine's stock libcd leaf calls.
#pragma once

#include <array>
#include <cstdint>

class Core;

namespace x4::music_cd {

using GuestBody = void (*)(Core *);

// Every address and literal below is read out of the authenticated SLUS_005.61 image with
// llvm-objdump over its text bytes (see docs/re-frontier.md RE-02: Ghidra's MIPS:BE:32 sleigh
// decodes this image incorrectly, so it is not the instrument).
//
// The state machine lives in the guest's XA/BGM module. Its per-field entry 0x800169D8 gates on
// `D_80141BD4 == 2` (`800169e0 lw $3,0x1bd4($3)` / `800169e8 bne $3,$2,0x80016B24`) and then loads
// the handler for the current machine state out of a 4-byte-stride jump table at 0x800F1AB0
// (`80016a10 sll $2,$2,0x2` / `80016a1c lw $2,0x1ab0($1)` / `80016a24 jalr $2`), indexed by the
// machine-state word `D_80139530`:
//
//   state 0 -> 0x80016B38   state 1 -> 0x80016B58   state 2 -> 0x80016BDC
//   state 3 -> 0x80016C5C   state 4 -> 0x80016D0C   state 5 -> 0x80016DAC
//   state 6 -> 0x80016E34   state 7 -> 0x80016E84
//
// so the state word is the NEXT command to issue and each handler re-issues its own until it is
// accepted, which makes the forward chain 7 -> 6 -> 5 -> 1. Every one of those handlers opens with
// `jal 0x800E5D20`, the stock Sony libcd `CdSync` leaf:
//
//   80016e40: 48 97 03 0c   jal 0xe5d20      (state 6, func_80016E34, a0=1 a1=0)
//   80016db8: 48 97 03 0c   jal 0xe5d20      (state 5, func_80016DAC, a0=1 a1=0)
//   80016b74: 48 97 03 0c   jal 0xe5d20      (state 1, func_80016B58, a0=1 a1=0x80139554)
//
// and each then compares v0 against CdlComplete and RETURNS without advancing if it is anything
// else (0x80016e4c / 0x80016dc4 / 0x80016b84, all `bne $2,$3`). `0x800E5D20` is a 4-instruction
// thunk (`addiu $sp,-0x18 / sw $ra / jal 0x800E68C8 / lw $ra / jr $ra`) onto the BIOS `CD_sync`,
// which opens with `jal 0x800E4DB0` (libetc VSync) and then polls the CD controller's own status
// register. This port completes CD commands synchronously and has no CD controller for that poll to
// observe, so the retained body cannot answer CdlComplete: the machine-state word stays where it
// is, `func_8001DDB0` never sees its handshake byte `D_80173C84` reach 2, and the post-movie guest
// never leaves sub-state 2.
//
// This owner therefore binds that one measured leaf to the framework's own stock-Sony completion
// authority (`psxport/runtime/psx/cd_control.h`), which is the same authority
// `x4::music_stream::setMode` already uses for the state-7 edge, and it completes each handler's
// command through the framework's blocking-control owner so the streaming read that state 1 issues
// actually starts.
//
// Scope is the three states on the 6 -> 5 -> 1 chain, because that is the chain the handshake
// depends on. State 7 is owned separately by `x4::music_stream` and never reaches this entry.
// States 2, 3 and 4 are on the pause/reset side of the machine, issue CdControlB rather than this
// CdControl entry, and are not required for the handshake; they keep the existing policy. The two
// callers of the leaf outside the step table (0x80016944 and 0x800188B8) are likewise untouched.
inline constexpr std::uint32_t kCdSyncEntry = 0x800E5D20u;
inline constexpr std::uint32_t kStepTable = 0x800F1AB0u;

// `D_80141BD4` must be 2 for the state machine to run at all, and `D_80139530` is the state index.
// `D_8013952C` is the sticky error byte; `0x80139554` is the shared CdControl result buffer that
// `func_80016B58` also tests for the shell-open bit 0x40.
inline constexpr std::uint32_t kMusicActive = 0x80141BD4u;
inline constexpr std::uint32_t kMachineState = 0x80139530u;
inline constexpr std::uint32_t kError = 0x8013952Cu;
inline constexpr std::uint32_t kResult = 0x80139554u;

// One measured step: the state word that selects the handler, and the CALL and RETURN edge of each of
// its two leaf calls. `parameter` and `result` are the literal a1/a2 the handler loads into its delay
// slots, so an owner that sees anything else was not reached by the guest body these addresses were
// read from.
//
// WHY BOTH THE CALL AND THE RETURN ARE FIELDS, and why that is not redundancy.
//
// `serveCdSync` and `serveCdControl` match on `core->r[31]`, which is what a `jal` LEAVES in r[31]:
// `call address + 8`, i.e. the instruction after the delay slot. Recording only the return address
// leaves the number with no stated derivation, and a wrong one is invisible — the lookup simply stops
// matching, the owner declines, and the call falls through to a policy this port cannot complete.
//
// That is not hypothetical: state 1's `CdControl` return was recorded as 0x80016BA4, which is the
// ADDRESS OF THE `jal` rather than what it leaves. The lookup therefore declined the one `CdlReadS`
// edge it claimed, the call fell into the retained-guest-body policy, and the product aborted in
// `x4::guest::callOriginal` after its measured 8-display-field bound on a CD status poll this port has
// no hardware to observe (player build 2026-09-27T19:01:13Z, `[x4-guest:error] fast_wait::CdControl
// original: guest call 0x800E5D90 to return address 0x80016BAC ... still at 0x800E50E8`).
//
// So the call address is now a field, `kJalReturnOffset` states the +8 once, and a `static_assert`
// holds the relationship for every step: a mis-entered return address breaks the BUILD instead of
// breaking the product. `tools/verify_music_cd.py` is the other half — it parses this table out of this
// file and diffs every entry against the authenticated bytes, because `tests/test_x4_music_cd.cpp`
// takes its expectations from these same constants and so can only prove the lookup is consistent with
// the table, never that the table matches SLUS_005.61.
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

// state 6, CdlSetfilter -> machine state 5; state 5, CdlSeekL -> 1; state 1, CdlReadS -> the
// handshake byte. Command IDs are the Psy-Q LIBCD.H values this image was linked against.
//
// Every `*Call` below is a `jal 0x0c` word read out of the image with llvm-objdump over
// `scratch/raw/x4_text.elf` (RE-02: Ghidra's MIPS:BE:32 sleigh decodes this image wrong):
//
//   80016e40: 48 97 03 0c   jal 0xe5d20    (state 6 CdSync)
//   80016e5c: 64 97 03 0c   jal 0xe5d90    (state 6 CdControl)
//   80016db8: 48 97 03 0c   jal 0xe5d20    (state 5 CdSync)
//   80016de8: 64 97 03 0c   jal 0xe5d90    (state 5 CdControl)
//   80016b74: 48 97 03 0c   jal 0xe5d20    (state 1 CdSync)
//   80016ba4: 64 97 03 0c   jal 0xe5d90    (state 1 CdControl)  -> r[31] = 0x80016bac
inline constexpr std::uint32_t kCommandComplete = 2u;
inline constexpr std::uint32_t kShellOpenBit = 0x40u;
inline constexpr std::uint32_t kCommandEntry = 0x800E5D90u;

// The 0x80016BA4 `jal` is spelled through the delay slot on purpose. It is the ONE step whose recorded
// return address was wrong (0x80016BA4, the `jal`'s own address), and writing it as
// `0x80016BA4 + kJalReturnOffset` means a reader can see the derivation in the table itself rather
// than having to take 0x80016BAC on trust. Every other step spells the measured return address, and
// the static_asserts below hold `return == call + kJalReturnOffset` for all six of them.
inline constexpr std::array<Step, 3> kSteps{
    Step{6u, 0x80016E34u, 0x80016E40u, 0x80016E48u, 0x80016E5Cu, 0x80016E64u, 0x0Du, 0x80175EE8u, 0u},
    Step{5u, 0x80016DACu, 0x80016DB8u, 0x80016DC0u, 0x80016DE8u, 0x80016DF0u, 0x15u, 0x80139514u, 0u},
    Step{
        1u, 0x80016B58u, 0x80016B74u, 0x80016B7Cu, 0x80016BA4u, 0x80016BA4u + kJalReturnOffset, 0x1Bu, 0u, 0x80139554u},
};
inline constexpr std::uint32_t kStepCount = static_cast<std::uint32_t>(kSteps.size());

// The derivation, held mechanically. A step whose return address is not its own `jal` plus the delay
// slot is a step the owner will never match, and that failure is silent.
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

// The three states on the 6 -> 5 -> 1 chain, named. These are references into `kSteps` rather than
// separate constants so that a lookup resolving to a step and a comparison against its name are the
// same object, not two equal-looking copies.
inline constexpr const Step &kSetFilterStep = kSteps[0];
inline constexpr const Step &kSeekStep = kSteps[1];
inline constexpr const Step &kReadStep = kSteps[2];

const Step *stepForSyncReturn(std::uint32_t returnAddress) noexcept;
const Step *stepForCommandReturn(std::uint32_t returnAddress) noexcept;

// Serve the leaf for one measured step edge. Both return false — leaving the caller's existing
// policy in force — when r[31] is not a measured edge, so nothing outside this subsystem can be
// absorbed by it. A measured edge whose command/parameter/result ABI differs from the image is a
// refusal, not a fallback: it means the owner is bound to an address it was not measured for.
bool serveCdSync(Core *core, GuestBody stockSync, GuestBody originalSync);
bool serveCdControl(Core *core, GuestBody stockControl);

// Image-scoped owner of the stock libcd CdSync leaf. Unmeasured callers keep the original body.
void registerOverrides(Core &core);

} // namespace x4::music_cd
