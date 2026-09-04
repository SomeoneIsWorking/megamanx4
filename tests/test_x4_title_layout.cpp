// SPDX-License-Identifier: AGPL-3.0-or-later
#include "title_layout.h"

#include <cstdio>

namespace {

int gChecks = 0;

#define CHECK(condition)                                                                                               \
  do {                                                                                                                 \
    ++gChecks;                                                                                                         \
    if (!(condition)) {                                                                                                \
      std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition);                                        \
      return 1;                                                                                                        \
    }                                                                                                                  \
  } while (0)

GuestProjectionPlan titlePlan(PresentationAspect aspect, int width, int margin) {
  GuestProjectionPlan plan;
  plan.aspect = aspect;
  plan.nativeExtent = {320, 240};
  plan.presentationExtent = {width, 240};
  plan.presentationHorizontalMargin = margin;
  return plan;
}

} // namespace

int main() {
  constexpr std::int32_t kRetailMenuX = 128 << 16;

  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Standard4x3, 320, 0)) == kRetailMenuX);
  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Wide16x9, 428, 54)) == (182 << 16));
  CHECK(x4::title_layout::centeredX(kRetailMenuX, titlePlan(PresentationAspect::Wide16x9, 320, 0)) == kRetailMenuX);

  std::fprintf(stderr, "x4_title_layout: %d checks passed\n", gChecks);
  return 0;
}
