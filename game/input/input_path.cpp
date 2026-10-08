#include "input_path.h"

#include "core.h"
#include "game.h"
#include "hle.h"
#include "pad_input.h"
#include "pad_layout.h"
#include "player_object.h"
#include "vsync_sync.h"
#include <lucent/log.h>

namespace x4::input_path {
namespace {

// Read through PadLens so the address stays owned by player_object.h.
uint16_t guestHeld(Core &core) {
  const guest::PadLens lens(core, guest::kPadHeldP1);
  return lens.held();
}

uint16_t guestPressed(Core &core) {
  const guest::PadLens lens(core, guest::kPadHeldP1);
  return lens.pressed();
}

// Libpad bytes 0-1 are status and pad id, not buttons.
struct PacketRecord {
  std::uint32_t bytes;
  std::uint16_t buttons;
};

PacketRecord packet(Core &core, std::uint32_t buffer) {
  PacketRecord record{0u, 0u};
  for (std::uint32_t index = 0; index < 4u; ++index) {
    record.bytes |= static_cast<std::uint32_t>(core.mem_r8(buffer + index)) << (8u * index);
  }
  record.buttons = core.mem_r16(buffer + 2u);
  return record;
}

} // namespace

void observeField(Core &core, const char *phase) {
  const Pad &pad = core.game->pad;
  const Hle &hle = core.game->hle;
  const PacketRecord slot0 = packet(core, pad::kSlot0Buffer);
  const PacketRecord slot1 = packet(core, pad::kSlot1Buffer);
  lucent::debug("x4-input-path",
                "{}: vbl={} repl(on={} tap=0x{:04X} tap_n={} hold=0x{:04X}) resolved(buttons=0x{:04X}) "
                "gate(initialized={} irq_started={} shouldService={}) "
                "guest(slot0_bytes=0x{:08X} slot0_buttons=0x{:04X} slot1_bytes=0x{:08X} "
                "slot1_buttons=0x{:04X} held=0x{:04X} pressed=0x{:04X})",
                phase,
                core.mem_r32(vsync::kVblankCounter),
                pad.repl_on,
                pad.repl_tap,
                pad.repl_tap_n,
                pad.repl_hold,
                pad.buttons,
                hle.bios_pad_initialized,
                hle.bios_pad_irq_started,
                hle.biosPadShouldService(),
                slot0.bytes,
                slot0.buttons,
                slot1.bytes,
                slot1.buttons,
                guestHeld(core),
                guestPressed(core));
}

} // namespace x4::input_path
