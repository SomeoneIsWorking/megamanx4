// music_stream.h -- native field ownership for X4's XA/BGM Setmode transition.
#pragma once

#include <cstdint>
#include <memory>

class Core;
class Coro;

namespace x4::music_stream {

using GuestBody = void (*)(Core *);
using GuestDispatch = void (*)(Core *, std::uint32_t);
using FieldYield = void (*)(Core &, std::uint32_t, std::uint32_t);

inline constexpr std::uint32_t kSetModeEntry = 0x80016E84u;
inline constexpr std::uint32_t kBeforeObjectsB = 0x800169D8u;
inline constexpr std::uint32_t kSetModeFieldReturn = 0x80016ED4u;
inline constexpr std::uint32_t kSetModeFields = 3u;
inline constexpr std::uint32_t kMusicActive = 0x80141BD4u;
inline constexpr std::uint32_t kMachineState = 0x80139530u;

// Preserve the retained state-7 body and command/result ABI while replacing only its VSync(3)
// call with a finite host-field yield.
void setMode(Core *core, GuestBody cdSync, GuestBody cdControl, FieldYield yieldFields);

// Runs the one retail 0x800169D8 transaction on a resumable stack only while state 7 can reach
// setMode's three-field fence. Ordinary music states stay on direct Lightrec guest dispatch.
class State {
public:
  explicit State(Core &core);
  ~State();

  State(const State &) = delete;
  State &operator=(const State &) = delete;

  [[nodiscard]] bool dispatchBeforeObjectsB(GuestDispatch dispatch);
  void yieldFields(std::uint32_t returnAddress, std::uint32_t fields);
  [[nodiscard]] bool pending() const;

private:
  Core &core_;
  GuestDispatch dispatch_ = nullptr;
  std::unique_ptr<Coro> transaction_;
};

void registerOverride(Core &core);

} // namespace x4::music_stream
