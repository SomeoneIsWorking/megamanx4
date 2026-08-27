#include "core.h"
#include "game.h"
#include "stream_startup.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>

namespace {

constexpr std::uint32_t kFieldEvent = 0xFFFFFFFFu;
constexpr std::uint32_t kCdTransactionEvent = 0xFFFFFFFEu;
constexpr std::uint32_t kStreamLba = 175155u;
constexpr std::uint32_t kFrameData = 0x80150000u;
constexpr std::uint32_t kFrameHeader = 0x80150100u;
constexpr std::uint32_t kGenericDmaIrqSlot = 0x8011CBA4u;
constexpr std::uint32_t kReadyCallbackSlot = 0x8011DD20u;
constexpr std::uint32_t kStSectorMode = 0x8013E1C0u;

std::vector<std::uint32_t> g_events;
std::uint32_t g_stGetNextCalls = 0u;
std::uint32_t g_cdReadMode = 0u;
std::uint32_t g_cdFilter = 0u;
std::uint32_t g_vlcInput = 0u;
std::uint32_t g_vlcTable = 0u;

std::uint8_t bcd(std::uint32_t value) {
  return static_cast<std::uint8_t>(((value / 10u) << 4u) | (value % 10u));
}

void recordField(Core &) {
  g_events.push_back(kFieldEvent);
}

bool recordCdTransaction(Core &core,
                         std::uint32_t lba,
                         std::uint32_t readMode,
                         std::uint32_t filter,
                         x4::stream_startup::FieldService serviceField) {
  g_events.push_back(kCdTransactionEvent);
  g_cdReadMode = readMode;
  g_cdFilter = filter;
  if (lba != kStreamLba || core.mem_r8(filter) != 1u) {
    return false;
  }

  // Model the shipping service's exact reset/filter/read wait placement. The function under test
  // owns this service call; these are native fields, never guest VSync dispatches.
  for (std::uint32_t phase = 0; phase < 3u; ++phase) {
    serviceField(core);
    serviceField(core);
    serviceField(core);
  }

  const std::uint32_t absolute = lba + 150u;
  core.mem_w8(0x8013964Du, bcd(absolute / (60u * 75u)));
  core.mem_w8(0x8013964Eu, bcd((absolute / 75u) % 60u));
  core.mem_w8(0x8013964Fu, bcd(absolute % 75u));
  return true;
}

void recordDispatch(Core *core, std::uint32_t entry) {
  g_events.push_back(entry);
  switch (entry) {
  case 0x800E61BCu: {
    const std::uint32_t absolute = core->r[4] + 150u;
    core->mem_w8(core->r[5] + 0u, bcd(absolute / (60u * 75u)));
    core->mem_w8(core->r[5] + 1u, bcd((absolute / 75u) % 60u));
    core->mem_w8(core->r[5] + 2u, bcd(absolute % 75u));
    break;
  }
  case 0x800E62C0u: {
    const std::uint32_t address = core->r[4];
    const auto fromBcd = [](std::uint32_t value) {
      return (value >> 4u) * 10u + (value & 0xFu);
    };
    const std::uint32_t minute = fromBcd(core->mem_r8(address + 0u));
    const std::uint32_t second = fromBcd(core->mem_r8(address + 1u));
    const std::uint32_t frame = fromBcd(core->mem_r8(address + 2u));
    core->r[2] = (minute * 60u + second) * 75u + frame - 150u;
    break;
  }
  case 0x800E83F4u:
    ++g_stGetNextCalls;
    if (g_stGetNextCalls < 3u) {
      core->r[2] = 1u;
    } else {
      core->mem_w32(core->r[4], kFrameData);
      core->mem_w32(core->r[5], kFrameHeader);
      core->mem_w32(0x801395B0u, 1u);
      core->r[2] = 0u;
    }
    break;
  case 0x800ED574u:
    g_vlcInput = core->r[4];
    g_vlcTable = core->r[5];
    break;
  default:
    break;
  }
}

bool check(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "x4_stream_startup: %s\n", message);
  }
  return condition;
}

bool verifyNoGuestWaits() {
  constexpr std::array<std::uint32_t, 6> kForbidden = {
      0x800E4DB0u, // VSync
      0x800E5C14u, // CdReset polling wrapper
      0x800E5D20u, // CdSync poll
      0x800E5D90u, // CdControl polling wrapper
      0x800E5FF4u, // CdControlB polling wrapper
      0x800E801Cu, // CdRead2 -> polling CdControl
  };
  for (const std::uint32_t event : g_events) {
    for (const std::uint32_t forbidden : kForbidden) {
      if (!check(event != forbidden, "finite STR startup dispatched a guest wait leaf")) {
        return false;
      }
    }
  }
  return true;
}

bool verifyOrder() {
  constexpr std::array<std::uint32_t, 10> kPrefix = {
      0x800190F0u,
      0x800ECDE0u,
      0x800ED084u,
      0x800E5A9Cu,
      0x800E8278u,
      0x800192F8u,
      0x80018FD0u,
      0x800E61BCu,
      kCdTransactionEvent,
      kFieldEvent,
  };
  if (!check(g_events.size() == 27u, "finite STR startup changed the event denominator")) {
    return false;
  }
  for (std::size_t index = 0; index < kPrefix.size(); ++index) {
    if (!check(g_events[index] == kPrefix[index], "finite STR startup changed its retail prefix/order")) {
      return false;
    }
  }
  for (std::size_t index = 9u; index < 18u; ++index) {
    if (!check(g_events[index] == kFieldEvent, "CD reset/filter/read waits were not nine native fields")) {
      return false;
    }
  }
  constexpr std::array<std::uint32_t, 7> kSuffix = {
      0x800E62C0u,
      0x80019228u,
      0x800E83F4u,
      kFieldEvent,
      0x800E83F4u,
      kFieldEvent,
      0x800E83F4u,
  };
  for (std::size_t index = 0u; index < kSuffix.size(); ++index) {
    if (!check(g_events[18u + index] == kSuffix[index], "first-frame polling order changed")) {
      return false;
    }
  }
  return check(g_events[25u] == 0x800ED574u && g_events[26u] == 0x800E8300u, "VLC/free-ring completion order changed");
}

bool verifyShippingCallbackRegistration(Core &core) {
  constexpr std::uint32_t kSentinel = 0xA5A55A5Au;
  constexpr std::uint32_t kStCdInterrupt = 0x800E80B0u;
  core.mem_w32(kGenericDmaIrqSlot, kSentinel);
  core.mem_w32(x4::stream_startup::kDmaChannel3CallbackSlot, kSentinel);
  core.mem_w32(kReadyCallbackSlot, kSentinel);
  core.mem_w32(kStSectorMode, kSentinel);

  x4::stream_startup::installReadCallbacks(core, 0x48u);
  if (!check(core.mem_r32(kGenericDmaIrqSlot) == kSentinel &&
                 core.mem_r32(x4::stream_startup::kDmaChannel3CallbackSlot) == kSentinel &&
                 core.mem_r32(kReadyCallbackSlot) == kSentinel && core.mem_r32(kStSectorMode) == kSentinel,
             "non-stream CdRead2 mode changed callback state")) {
    return false;
  }

  x4::stream_startup::installReadCallbacks(core, 0x148u);
  if (!check(core.mem_r32(kGenericDmaIrqSlot) == kSentinel,
             "stream setup overwrote generic IRQ3 instead of the per-channel DMA3 slot") ||
      !check(core.mem_r32(x4::stream_startup::kDmaChannel3CallbackSlot) == x4::stream_startup::kStDataReadyCallback,
             "stream setup did not publish StDataReadyCallback in DMACallback channel 3") ||
      !check(core.mem_r32(kReadyCallbackSlot) == kStCdInterrupt,
             "stream setup did not publish StCdInterrupt in libcd's sync callback slot") ||
      !check(core.mem_r32(kStSectorMode) == 1u, "2048-byte stream mode did not publish sector framing 1")) {
    return false;
  }

  x4::stream_startup::installReadCallbacks(core, 0x120u);
  return check(core.mem_r32(kStSectorMode) == 0u, "whole-sector stream mode did not publish sector framing 0");
}

} // namespace

int main() {
  auto game = std::make_unique<Game>();
  Core &core = game->core;
  constexpr std::uint32_t kStack = 0x801FFF00u;
  constexpr std::uint32_t kReturnAddress = 0x81234567u;
  constexpr std::array<std::uint32_t, 4> kSaved = {0x16161616u, 0x17171717u, 0x18181818u, 0x19191919u};

  core.r[29] = kStack;
  core.r[31] = kReturnAddress;
  core.r[16] = kSaved[0];
  core.r[17] = kSaved[1];
  core.r[18] = kSaved[2];
  core.r[19] = kSaved[3];
  core.r[4] = kStreamLba;
  core.r[5] = 10u;
  core.r[6] = 0xA2A2A2A2u;
  core.r[7] = 0x80160000u;
  core.mem_w32(kStack + 16u, 0x4000u);
  core.mem_w32(kStack + 20u, 0x80161000u);
  core.mem_w32(kStack + 24u, 0x80162000u);
  core.mem_w32(kStack + 28u, 0x80163000u);
  core.mem_w32(kStack + 32u, 0u);
  core.mem_w32(kStack + 36u, 0x80164000u);
  for (std::uint32_t byte = 0u; byte < 32u; ++byte) {
    core.mem_w8(kFrameHeader + byte, static_cast<std::uint8_t>(0x40u + byte));
  }
  core.mem_w16(kFrameHeader + 16u, 319u);
  core.mem_w16(kFrameHeader + 18u, 239u);

  g_events.clear();
  g_stGetNextCalls = 0u;
  g_cdReadMode = 0u;
  g_cdFilter = 0u;
  g_vlcInput = 0u;
  g_vlcTable = 0u;
  bool ok = verifyShippingCallbackRegistration(core);
  x4::stream_startup::run(core, recordDispatch, recordField, recordCdTransaction);

  ok = verifyNoGuestWaits() && ok;
  ok = check(core.r[2] == 0u, "finite STR startup did not return success") && ok;
  ok = check(core.r[29] == kStack && core.r[31] == kReturnAddress, "caller stack/RA were not restored") && ok;
  ok = check(core.r[16] == kSaved[0] && core.r[17] == kSaved[1] && core.r[18] == kSaved[2] && core.r[19] == kSaved[3],
             "callee-saved registers were not restored") &&
       ok;
  ok = check(g_cdReadMode == 328u && g_cdFilter == 0x80175EE8u,
             "native CD transaction received non-retail mode/filter") &&
       ok;
  ok = check(g_stGetNextCalls == 3u, "first-frame wait did not preserve two retries then success") && ok;
  ok = check(core.mem_r32(0x801395E0u) == 0xA2A2A2A2u && core.mem_r32(0x80139650u) == kStreamLba,
             "stream arguments were not published") &&
       ok;
  ok = check(core.mem_r16(0x80139600u) == 320u && core.mem_r16(0x80139602u) == 240u,
             "first-frame dimensions were not aligned as retail") &&
       ok;
  for (std::uint32_t byte = 0u; byte < 32u; ++byte) {
    const bool dimensionByte = byte >= 16u && byte < 20u;
    ok = check(dimensionByte || core.mem_r8(0x801395F0u + byte) == core.mem_r8(kFrameHeader + byte),
               "first-frame header copy changed") &&
         ok;
  }
  ok = check(g_vlcInput == kFrameData && g_vlcTable == 0x80161000u, "VLC decode received the wrong input/table") && ok;
  ok = verifyOrder() && ok;

  if (ok) {
    core.r[29] = kStack;
    core.r[31] = kReturnAddress;
    core.r[16] = kSaved[0];
    core.r[17] = kSaved[1];
    core.r[18] = kSaved[2];
    core.r[19] = kSaved[3];
    core.r[4] = kStreamLba;
    core.r[5] = 10u;
    core.r[6] = 0xA2A2A2A2u;
    core.r[7] = 0x80160000u;
    core.mem_w32(kStack + 32u, 1u);
    g_events.clear();
    g_stGetNextCalls = 2u;
    g_cdReadMode = 0u;
    x4::stream_startup::run(core, recordDispatch, recordField, recordCdTransaction);
    ok = check(g_cdReadMode == 456u, "alternate retail stream flavor did not select read mode 456") &&
         verifyNoGuestWaits();
  }

  if (!ok) {
    return 1;
  }
  std::puts("x4_stream_startup: finite STR state, native fields, first-frame decode, and no guest waits passed");
  return 0;
}
