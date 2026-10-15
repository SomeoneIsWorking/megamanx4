#pragma once

#include "guest_execution.h"

#include <cstdint>
#include <memory>

class Core;
class Coro;

namespace x4::music_stream {

using GuestBody = void (*)(Core *);
// Yields the fields of the guest VSync call in r[4], returning to r[31].
using FieldYield = void (*)(Core &);

inline constexpr std::uint32_t kSetModeEntry = 0x80016E84u;
inline constexpr std::uint32_t kBeforeObjectsB = 0x800169D8u;
inline constexpr std::uint32_t kSetModeFieldReturn = 0x80016ED4u;
inline constexpr std::uint32_t kSetModeFields = 3u;
inline constexpr std::uint32_t kMusicActive = 0x80141BD4u;
inline constexpr std::uint32_t kMachineState = 0x80139530u;

// State-7 body at 0x80016E84 with its VSync(3) replaced by a host field yield.
void setMode(Core *core, GuestBody cdSync, GuestBody cdControl, FieldYield yieldFields);

// Runs 0x800169D8 on a resumable stack only while state 7 can reach setMode's field yield.
class State {
public:
  explicit State(Core &core);
  ~State();

  State(const State &) = delete;
  State &operator=(const State &) = delete;

  [[nodiscard]] bool dispatchBeforeObjectsB(guest::Dispatch dispatch);
  // The guest's VSync(3) at 0x80016ED4: a0 is the count, ra the return edge.
  void yieldFields();
  [[nodiscard]] bool pending() const;

private:
  Core &core_;
  guest::Dispatch dispatch_ = nullptr;
  std::unique_ptr<Coro> transaction_;
};

void registerOverride(Core &core);

} // namespace x4::music_stream
