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

// Owns "an STR movie holds the picture": from the STR startup (`beginStream`) through the end of the
// three-fence cleanup transaction. The XA/BGM stream also sets the CD pump's stream bit, so that bit
// says nothing about movies.
class State {
public:
  explicit State(Core &core);
  State(Core &core, SuspendField suspendField);

  void beginStream();
  void abandonStream();
  void begin();
  void yieldFields(std::uint32_t returnAddress, std::uint32_t fields);
  void complete();

  [[nodiscard]] bool pending() const;
  [[nodiscard]] bool streaming() const;
  [[nodiscard]] bool ownsPicture() const;
  [[nodiscard]] Phase phase() const;
  [[nodiscard]] std::uint32_t completedFields() const;

private:
  Core &core_;
  SuspendField suspendField_;
  Phase phase_ = Phase::Idle;
  bool streaming_ = false;
  std::uint32_t completedFields_ = 0u;
};

// Native owner of movie cleanup 0x80018E50: ordinary calls stay in the guest; controller commands
// are synchronous and the three VSync fences are host fields.
void run(Core &core, State &state, GuestDispatch dispatch, ControllerReset resetController);
void run(Core *core);
void registerOverride(Core &core);

} // namespace x4::movie_cleanup
