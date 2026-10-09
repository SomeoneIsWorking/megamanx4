// SPDX-License-Identifier: AGPL-3.0-or-later
#include "hud_anchor.h"

#include "core.h"

#include <algorithm>

namespace x4::hud {
namespace {

// GP0 packet layout: tag word, then the command byte at +7; rectangles keep xy at +8.
constexpr std::uint32_t kTagLengthOffset = 3;
constexpr std::uint32_t kCommandOffset = 7;
constexpr std::uint32_t kFirstVertexOffset = 8;

constexpr std::uint8_t kPolygonClass = 0x20;
constexpr std::uint8_t kRectangleClass = 0x60;
constexpr std::uint8_t kClassMask = 0xE0;
constexpr std::uint8_t kQuadBit = 0x08;
constexpr std::uint8_t kTexturedBit = 0x04;
constexpr std::uint8_t kGouraudBit = 0x10;

struct Vertices {
  std::uint32_t count;
  std::uint32_t stride;
};

// Polygon vertices follow the colour word; a shaded vertex is preceded by its colour, a textured one followed by uv.
Vertices verticesOf(std::uint8_t command) {
  const std::uint32_t count = (command & kQuadBit) != 0 ? 4u : 3u;
  const std::uint32_t stride =
      4u + ((command & kTexturedBit) != 0 ? 4u : 0u) + ((command & kGouraudBit) != 0 ? 4u : 0u);
  return {count, stride};
}

} // namespace

ArenaPositions HudAnchor::positions(Core &core) {
  ArenaPositions positions{};
  for (std::size_t i = 0; i < kArenaCursors.size(); ++i) {
    positions[i] = core.mem_r32(kArenaCursors[i]);
  }
  return positions;
}

void HudAnchor::shiftPacket(Core &core, std::uint32_t packet) const {
  const std::uint8_t command = core.mem_r8(packet + kCommandOffset);
  const std::uint8_t kind = command & kClassMask;
  std::uint32_t count = 0;
  std::uint32_t stride = 0;
  if (kind == kRectangleClass) {
    count = 1;
  } else if (kind == kPolygonClass) {
    const Vertices vertices = verticesOf(command);
    count = vertices.count;
    stride = vertices.stride;
  }
  if (count == 0) {
    return;
  }
  int leftmost = 0;
  for (std::uint32_t i = 0; i < count; ++i) {
    const int x = static_cast<std::int16_t>(core.mem_r16(packet + kFirstVertexOffset + i * stride));
    leftmost = i == 0 ? x : std::min(leftmost, x);
  }
  const int shift = leftmost < kCentre ? -margin() : margin();
  for (std::uint32_t i = 0; i < count; ++i) {
    const std::uint32_t address = packet + kFirstVertexOffset + i * stride;
    core.mem_w16(address, static_cast<std::uint16_t>(static_cast<std::int16_t>(core.mem_r16(address)) + shift));
  }
}

void HudAnchor::anchor(Core &core, const ArenaPositions &before) const {
  if (margin() == 0) {
    return;
  }
  const ArenaPositions after = positions(core);
  for (std::size_t arena = 0; arena < kArenaCursors.size(); ++arena) {
    std::uint32_t packet = before[arena];
    while (packet < after[arena]) {
      shiftPacket(core, packet);
      packet += (static_cast<std::uint32_t>(core.mem_r8(packet + kTagLengthOffset)) + 1u) * 4u;
    }
  }
}

} // namespace x4::hud
