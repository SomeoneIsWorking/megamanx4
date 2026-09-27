// input_path.cpp — the read-only per-field input-path observer declared in input_path.h.
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

// The guest's decoded trio is a LENS over the words kInputRouterFn writes; reading it through
// PadLens rather than by hand is what keeps this observer from re-deriving an address that
// player_object.h owns.
uint16_t guestHeld(Core &core) {
  const guest::PadLens lens(core, guest::kPadHeldP1);
  return lens.held();
}

uint16_t guestPressed(Core &core) {
  const guest::PadLens lens(core, guest::kPadHeldP1);
  return lens.pressed();
}

// One libpad packet, printed so that NOTHING about its layout has to be inferred by whoever reads
// the line back.
//
// The frontier probe in tools/live_play.py read the packet's first two bytes and reported a
// constant 0x4100 for several runs, which reads exactly like "the taps never arrived" and is in fact
// the packet's STATUS and PAD-ID header. The first version of THIS observer then made the mirror
// mistake in the other direction: it packed the four bytes into one word and the reader sliced the
// LOW halfword, so a delivered 0xFFF7 button halfword was read as 0x4100 and the run reported the
// break at the write. Both are the same error, so the record now carries the bytes AND the two
// halfwords, and the reader cross-checks them: a line whose byte slice disagrees with its own
// reported halfword is a line the reader REFUSES rather than one it interprets.
//
// The halfword is read with mem_r16 at +2, which is how the GUEST reads it, so the value printed
// here is the guest's value and not this file's idea of the byte order.
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
