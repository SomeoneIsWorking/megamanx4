// vsync_sync.h — Mega Man X4's display-field service AND the libetc VSync entry owner.
//
// ONE owner for 0x800E4DB0. Why that matters is the whole story of this file, so read
// the deleted game/core/movie_field.h before changing anything here.
#pragma once

#include <cstdint>

class Core;

namespace x4::bios_threads {
class Service;
}

namespace x4::vsync {

// Retail SLUS_005.61, SHA-1 213733031136d095ca275d6957695aa25011cfa5.
//
// The full libetc VSync entry, and the half-open four-byte window that admits exactly it to the
// framework's hardware-service table. The native frame shell owns timing, so no guest VSync mode
// is forbidden here — the entry is SERVED, and every mode below is the retail decision read from
// these bytes rather than a port policy.
inline constexpr std::uint32_t kVSync = 0x800E4DB0u;
inline constexpr std::uint32_t kVSyncEntryEnd = 0x800E4DB4u;

// The measured state libetc VSync keeps. Each of these is a word the retail body at 0x800E4DB0
// reads or writes, named here so the owner and its tests read the same numbers.
//
//   kVblankCounter  0x8011DC50  the VBlank field counter. The IRQ-0 handler 0x800E56FC increments
//                                it once per field (0x800E5700 read / 0x800E5728 write), the init
//                                0x800E56A4 zeroes it (0x800E56C8), and BOTH of VSync's counter
//                                waits (0x800E4F08 and 0x800E4F70) read it. It is the one clock
//                                the whole field contract is expressed in.
//   kRegisterCell0  0x8011CB84  a cell holding 0x1F801814 (GPUSTAT) in the retail image. Read, never
//                                written by any instruction in the resident text, so the register it
//                                names is the image's own constant.
//   kRegisterCell1  0x8011CB88  a cell holding 0x1F801110 (root counter 1, HBlank-clocked).
//   kLastSample     0x8011CB8C  VSync's own previous RCNT1 sample. Its only reader is VSync itself
//                                (0x800E4DDC) and its only writer is VSync (0x800E4EDC).
//   kLastSync       0x8011CB90  the field counter at VSync's last completed sync. Only VSync reads
//                                (0x800E4E18, 0x800E4E30) or writes (0x800E4ECC) it.
inline constexpr std::uint32_t kVblankCounter = 0x8011DC50u;
inline constexpr std::uint32_t kRegisterCell0 = 0x8011CB84u;
inline constexpr std::uint32_t kRegisterCell1 = 0x8011CB88u;
inline constexpr std::uint32_t kLastSample = 0x8011CB8Cu;
inline constexpr std::uint32_t kLastSync = 0x8011CB90u;

// THE FIELD-COUNT RULE, read from 0x800E4E00..0x800E4E44 plus the wait helper 0x800E4EF8.
//
// `a1` is only the helper's spin budget (0x800E4EFC shifts it left by 15 and 0x800E4F38 aborts when
// it reaches -1 with the retail "VSync: timeout\n" at 0x80011900), so a positive mode's field count
// is entirely in `a0`, and `a0` is compared against the VBlank counter by 0x800E4F10/0x800E4F78.
//
//   mode <  0  0x800E4DE8 bgez skips the waits; 0x800E4DF0 returns [0x8011DC50]. No state change.
//   mode == 1  0x800E4E04 beq returns s1 immediately, skipping BOTH waits AND the state write.
//   mode == 0  0x800E4E2C targets kLastSync, which the counter has already passed, so the first
//              wait is satisfied and only the second (0x800E4E5C, target = counter + 1) costs a
//              field: ONE field.
//   mode >= 2  0x800E4E14 targets kLastSync + mode - 1, so `mode - 1` fields, then one more.
//
//   fields(mode) = 0 for mode < 0 and mode == 1, and max(mode, 1) otherwise. That is 1 field for
//   VSync(0) and exactly `mode` fields for VSync(2)/VSync(3) — which is why the two title owners
//   that already replaced a VSync(3) fence park three fields (movie_cleanup's kSettlingFields).
inline constexpr std::uint32_t fieldsForMode(std::int32_t mode) {
  return mode == 1 ? 0u : (mode == 0 ? 1u : static_cast<std::uint32_t>(mode));
}

// Advance exactly one retail display field at the native frame boundary.
void deliverField(Core &core);

// Park exactly ONE host field and leave libetc VSync(0)'s unconsumed zero result in v0. This is the
// primitive `serveVSync` is built from, and it is also the direct seam a title owner with a
// measured one-field fence of its own uses. `returnAddress` is asserted against r[31] because a
// `jal`ed leaf's continuation IS r[31] and a mismatch means the caller passed a different address
// than the guest's own call did.
void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads);

// Serve the libetc VSync entry for every mode the retail body defines.
void serveVSync(Core *core);

// Install `serveVSync` as the authenticated image-scoped owner of the entry. The title's own
// override is consulted BEFORE the framework's hardware-service table
// (psxport/runtime/cpu/native_dispatch.cpp, resolveHostDispatch step 1), so this is the only
// answer 0x800E4DB0 gets; GameConfig's `.vsyncTrap` stays as the fail-fast backstop and as what
// satisfies the framework's native-frame-loop preflight.
void registerOverrides(Core &core);

} // namespace x4::vsync
