#include "core.h"
#include "game.h"
#include "stream_interrupt.h"

#include <cstdint>
#include <cstdio>
#include <memory>

namespace {

constexpr std::uint32_t kStack = 0x801FFF00u;
constexpr std::uint32_t kReturnAddress = 0x81234567u;
constexpr std::uint32_t kResponse = 0x80150000u;
constexpr std::uint32_t kSyncResult = 0x8011DFF9u;
constexpr std::uint32_t kDataReadyResult = 0x8011DFFAu;
constexpr std::uint32_t kDataReadyResponse = 0x8013BA88u;

bool g_consumed = false;
bool g_responseMatched = false;

void retainedStCdInterrupt(Core *core) {
  core->r[29] -= 64u;
  core->mem_w32(core->r[29] + 56u, core->r[31]);

  // Exact nested edge at retail 0x800E8564: CdReady(1, sp+48), returning to 0x800E856C.
  core->r[4] = 1u;
  core->r[5] = core->r[29] + 48u;
  core->r[31] = x4::stream_interrupt::kCdReadyReturn;
  g_consumed = x4::stream_interrupt::consumeCompletedCallback(*core);

  g_responseMatched = true;
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    g_responseMatched =
        g_responseMatched && core->mem_r8(core->r[29] + 48u + byte) == static_cast<std::uint8_t>(0xA0u + byte);
  }

  core->r[31] = core->mem_r32(core->r[29] + 56u);
  core->r[29] += 64u;
}

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_stream_interrupt: %s\n", message);
  }
  return condition;
}

void publishResponse(Core &core, std::uint32_t address, std::uint8_t firstByte) {
  for (std::uint32_t byte = 0u; byte < 8u; ++byte) {
    core.mem_w8(address + byte, static_cast<std::uint8_t>(firstByte + byte));
  }
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  constexpr std::uint32_t kStatus = 4u;

  core.r[29] = kStack;
  core.r[31] = kReturnAddress;
  core.r[4] = kStatus;
  core.r[5] = kResponse;
  core.mem_w8(kSyncResult, static_cast<std::uint8_t>(kStatus));
  core.mem_w8(0x8011DFF8u, 0x5Au);
  publishResponse(core, kResponse, 0xA0u);

  bool ok = check(!x4::stream_interrupt::consumeCompletedCallback(core),
                  "CdReady was consumed outside its top-level StCdInterrupt scope");
  x4::stream_interrupt::run(core, retainedStCdInterrupt);

  ok = check(g_consumed, "the measured nested CdReady edge was not consumed") && ok;
  ok = check(g_responseMatched, "the callback's eight-byte response was not copied to the retail stack slot") && ok;
  ok = check(core.r[2] == kStatus, "the callback status was not returned as CdReady's result") && ok;
  ok = check(core.mem_r8(kSyncResult) == 0u, "the consumed libcd sync result remained pending") && ok;
  ok = check(core.mem_r8(0x8011DFF8u) == 0x5Au, "the unrelated ready-result byte was changed") && ok;
  ok = check(core.r[29] == kStack && core.r[31] == kReturnAddress,
             "the retained StCdInterrupt body did not restore its caller stack/RA") &&
       ok;
  ok = check(!x4::stream_interrupt::consumeCompletedCallback(core),
             "the callback scope leaked after StCdInterrupt returned") &&
       ok;

  // CdlDataReady publishes both ready and sync completion state. CD_ready consumes the ready pair
  // first, leaving the sync pair pending for the same reason as the retail libcd implementation.
  constexpr std::uint32_t kDataReadyStatus = 4u;
  g_consumed = false;
  g_responseMatched = false;
  core.r[4] = kDataReadyStatus;
  core.r[5] = kResponse;
  core.mem_w8(kSyncResult, static_cast<std::uint8_t>(kDataReadyStatus));
  core.mem_w8(kDataReadyResult, static_cast<std::uint8_t>(kDataReadyStatus));
  publishResponse(core, kResponse, 0x30u);
  publishResponse(core, kDataReadyResponse, 0xA0u);

  x4::stream_interrupt::run(core, retainedStCdInterrupt);
  ok = check(g_consumed, "the CdlDataReady CdReady edge was not consumed") && ok;
  ok = check(g_responseMatched, "the higher-priority ready response was not copied") && ok;
  ok = check(core.r[2] == kDataReadyStatus, "the ready result was not returned") && ok;
  ok = check(core.mem_r8(kDataReadyResult) == 0u, "the consumed data-ready result remained pending") && ok;
  ok = check(core.mem_r8(kSyncResult) == kDataReadyStatus,
             "CdlDataReady consumption incorrectly cleared the pending sync result") &&
       ok;

  if (!ok) {
    return 1;
  }
  std::puts("x4_stream_interrupt: callback result consumed once with no guest timing query");
  return 0;
}
