#pragma once

#include <cstdint>

class Core;

namespace x4::movie_cleanup {

using GuestDispatch = void (*)(Core *, std::uint32_t);
using ControllerReset = void (*)(Core &);
using SuspendField = void (*)(Core &);

inline constexpr std::uint32_t kEntry = 0x80018E50u;
inline constexpr std::uint32_t kDisplayFieldReturn = 0x80018E84u;
inline constexpr std::uint32_t kResetFenceReturn = 0x80018EBCu;
inline constexpr std::uint32_t kSetModeFenceReturn = 0x80018EDCu;
inline constexpr std::uint32_t kDisplayFields = 1u;
inline constexpr std::uint32_t kSettlingFields = 3u;
inline constexpr std::uint32_t kTotalFields = kDisplayFields + 2u * kSettlingFields;

enum class Phase : std::uint8_t {
  Idle,
  BeforeDisplayFence,
  DisplayFence,
  AfterDisplayFence,
  ResetFence,
  AfterResetFence,
  SetModeFence,
  AfterSetModeFence,
};

// Tracks the three authenticated VSync edges in the retained movie-cleanup transaction. The active
// phase is also the frame driver's ownership signal after Pause releases the CD stream bit.
class State {
public:
  explicit State(Core &core);
  State(Core &core, SuspendField suspendField);

  void begin();
  void yieldFields(std::uint32_t returnAddress, std::uint32_t fields);
  void complete();

  [[nodiscard]] bool pending() const;
  [[nodiscard]] Phase phase() const;
  [[nodiscard]] std::uint32_t completedFields() const;

private:
  Core &core_;
  SuspendField suspendField_;
  Phase phase_ = Phase::Idle;
  std::uint32_t completedFields_ = 0u;
};

// Complete native owner of SLUS_005.61 movie cleanup 0x80018E50. Ordinary calls remain in the
// authenticated guest executable; the only semantic ownership changes are synchronous controller
// reset/commands and the three finite host-field fences.
void run(Core &core, State &state, GuestDispatch dispatch, ControllerReset resetController);
void run(Core *core);
void registerOverride(Core &core);

} // namespace x4::movie_cleanup
