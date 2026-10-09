// Hermetic gate for game/input/sequence_skip.{h,cpp}: the Cross edge raised while Start is held in the briefing.
#include "sequence_skip.h"

#include "core.h"
#include "game.h"
#include "player_object.h"

#include <cstdio>
#include <memory>

namespace {

using x4::guest::kPadHeldP1;
using x4::guest::kPadPressedP1;
using x4::guest::kPadPrevP1;
using x4::sequence_skip::kAdvanceCadence;
using x4::sequence_skip::kBriefingState;
using x4::sequence_skip::kBriefingSubState;
using x4::sequence_skip::kCrossMask;
using x4::sequence_skip::kEngineAddress;
using x4::sequence_skip::kEngineStateOffset;
using x4::sequence_skip::kEngineSubStateOffset;
using x4::sequence_skip::kStartMask;
using x4::sequence_skip::SequenceSkip;

#define CHECK(cond)                                                                                                    \
  do {                                                                                                                 \
    if (!(cond)) {                                                                                                     \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                                             \
      return false;                                                                                                    \
    }                                                                                                                  \
  } while (0)

struct Fixture {
  std::unique_ptr<Game> game = std::make_unique<Game>();
  Core &core = game->core;

  void engine(std::uint8_t state, std::uint8_t subState) {
    core.mem_w8(kEngineAddress + kEngineStateOffset, state);
    core.mem_w8(kEngineAddress + kEngineSubStateOffset, subState);
  }
  // What the retail router leaves for a field: held now, held last field, and the edge between them.
  void pad(std::uint16_t held, std::uint16_t previous) {
    core.mem_w16(kPadHeldP1, held);
    core.mem_w16(kPadPrevP1, previous);
    core.mem_w16(kPadPressedP1, static_cast<std::uint16_t>(held & ~previous));
  }
  std::uint16_t held() const {
    return core.mem_r16(kPadHeldP1);
  }
  std::uint16_t pressed() const {
    return core.mem_r16(kPadPressedP1);
  }
};

bool verifyBriefingDetection(Fixture &f) {
  f.engine(kBriefingState, kBriefingSubState);
  CHECK(SequenceSkip::inBriefing(f.core));
  f.engine(kBriefingState, kBriefingSubState - 1);
  CHECK(!SequenceSkip::inBriefing(f.core));
  f.engine(kBriefingState - 1, kBriefingSubState);
  CHECK(!SequenceSkip::inBriefing(f.core));
  return true;
}

bool verifyStartRaisesTheAdvanceEdgeOnItsCadence(Fixture &f) {
  SequenceSkip skip;
  f.engine(kBriefingState, kBriefingSubState);
  std::uint16_t previous = kStartMask;
  int edges = 0;
  for (std::uint32_t field = 0; field < 4 * kAdvanceCadence; ++field) {
    f.pad(kStartMask, previous);
    skip.afterPadRoute(f.core);
    const bool advanced = (f.pressed() & kCrossMask) != 0;
    CHECK(advanced == (field % kAdvanceCadence == 0));
    CHECK((f.held() & kStartMask) != 0);
    edges += advanced ? 1 : 0;
    previous = f.held();
  }
  CHECK(edges == 4);
  CHECK(skip.fieldsSkipped() == 4 * kAdvanceCadence);
  return true;
}

bool verifyOnlyStartInTheBriefingSkips(Fixture &f) {
  SequenceSkip skip;
  f.engine(kBriefingState, kBriefingSubState);
  f.pad(0, 0);
  skip.afterPadRoute(f.core);
  CHECK(f.held() == 0 && f.pressed() == 0);
  CHECK(skip.fieldsSkipped() == 0);

  f.engine(kBriefingState, 0);
  f.pad(kStartMask, 0);
  skip.afterPadRoute(f.core);
  CHECK((f.pressed() & kCrossMask) == 0 && (f.held() & kCrossMask) == 0);

  // Leaving the briefing restarts the cadence at an edge.
  f.engine(kBriefingState, kBriefingSubState);
  f.pad(kStartMask, kStartMask);
  skip.afterPadRoute(f.core);
  CHECK((f.pressed() & kCrossMask) != 0);
  f.engine(kBriefingState, 0);
  skip.afterPadRoute(f.core);
  CHECK(skip.fieldsSkipped() == 0);
  return true;
}

} // namespace

int main() {
  Fixture fixture;
  if (!verifyBriefingDetection(fixture) || !verifyStartRaisesTheAdvanceEdgeOnItsCadence(fixture) ||
      !verifyOnlyStartInTheBriefingSkips(fixture)) {
    return 1;
  }
  std::fputs("x4_sequence_skip: ok\n", stderr);
  return 0;
}
