#include "vram_rect_queue.h"

#include <cstdint>
#include <cstdio>

int main() {
  namespace vr = x4::vram_rect;
  // The animation word of g_Player's index 247 in the demo stage: 25 bands, stream offset 0x1DFB4.
  constexpr std::uint32_t kWord = 0x0191DFB4u;
  constexpr std::uint32_t kBlob = 0x801789A8u;
  const bool passed = vr::bandCount(kWord) == 25 && vr::streamAddress(kBlob, kWord) == kBlob + 0x1DFB4u &&
                      vr::streamAddress(kBlob, 0x02008B0Cu) == kBlob + 0x8B0Cu && vr::bandCount(0x02008B0Cu) == 32;
  if (!passed) {
    std::fprintf(stderr, "x4_vram_rect_queue: stream offset or band count differs from retail 0x80015F20-0x80015F50\n");
    return 1;
  }
  std::puts("x4_vram_rect_queue: 20-bit stream offset and 12-bit band count passed");
  return 0;
}
