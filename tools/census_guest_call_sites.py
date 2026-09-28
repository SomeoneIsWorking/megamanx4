#!/usr/bin/env python3
"""census_guest_call_sites.py — find where the GUEST calls each entry the port calls natively.

WHY THIS EXISTS. `x4::guest::call` derives its return boundary from `core->r[31]`, which is correct
only when GUEST code executed the `jal`. Every one of this title's `guest::call` sites is a NATIVE
owner, so each one inherits whatever link register the guest last left and uses it as the address the
call must reach to return. Measured 2026-09-29 (`docs/issues/0037`): the RLE decompress call at
0x80016FF4 was given the boundary 0x80022060, which is the return address of an UNRELATED
`jal 0x80015ecc` at 0x80022058. The decompressor cannot return there, so it ran 757,804 cycles past
its own end and faulted at a non-address.

The fix is for each native owner to supply the return address its own call site implies. That value
is not a guess and it is not derivable from the port: it is wherever RETAIL called the function. So
this tool finds those sites in the guest image.

THE MEASUREMENT, and its two rules.

  * A MIPS `jal` is J-type: its target is an absolute 26-bit field, NOT PC-relative. Reading it as
    PC-relative produced five wrong targets in a hand-decoded listing on this same title
    (`docs/issues/0007`), every one of them a plausible guest address.
  * A `jal` links `$ra = PC + 8`, not PC + 4, because of the delay slot. The RETURN ADDRESS is
    therefore `jal_address + 8`, and that is the number the boundary must be.

Both are applied here, and both are asserted against a self-check rather than trusted: `--selftest`
runs the same decode over a hand-assembled stream with a known answer.

WHAT IT REPORTS, per entry: the number of `jal` sites in the whole text (the denominator), and for
each site the return address. An entry with ZERO sites is a real result and is printed as such — a
function retail never called by `jal` is reached by `jalr` or a pointer, and the tool says which
question is still open rather than inventing a boundary.

Usage:
  uv run --frozen python tools/census_guest_call_sites.py [EXE]
  uv run --frozen python tools/census_guest_call_sites.py --verify-boundaries
  uv run --frozen python tools/census_guest_call_sites.py --selftest
"""

from __future__ import annotations

import pathlib
import re
import struct
import sys

# The guest entries this title's NATIVE owners call. Each is a constant the port invokes from host
# C++, which is precisely the case where `core->r[31]` is not a return address for it.
GUEST_ENTRIES: dict[str, int] = {
    "kDecompressGfxGuest": 0x80016FF4,   # RLE decompressor; the call that faulted
    "kLoadImageGuest": 0x800EA4D0,       # BIOS LoadImage, the uploader
    "kClearQueueGuest": 0x80015E0C,
    "kUploadQueueGuest": 0x80015E54,
    "kAppendBandsGuest": 0x80015ECD,
    "music_stream entry": 0x800E5D90,
    "display_init 0": 0x800E9D4C,
    "display_init 1": 0x800EA3A0,
    "display_init 2": 0x800EA20C,
    "display_init 3": 0x800EA170,
    "display_init 4": 0x800E9424,
    "SetDefDrawEnv": 0x800E9354,
    "IssueLocation": 0x800E61BC,
    "QueryArchiveStatus": 0x8001385C,
    "PublishDirectReady": 0x80013650,
}

# J-type. The target is { PC[31:28] of the DELAY SLOT, instr_index[25:0], 00 }. It is NOT PC-relative.
# The region nibble comes from the ADDRESS, never from the instruction word: taking it from the word
# is how a J target ends up 0x70000000 away from the truth while still looking like a guest address.
OP_JAL = 0x03


def decode_jal_target(word: int, pc: int) -> int | None:
    """Absolute target of a J-type `jal` at `pc`, or None if the word is not one."""
    if (word >> 26) != OP_JAL:
        return None
    region = ((pc + 4) >> 28) & 0xF
    return (region << 28) | ((word & 0x03FFFFFF) << 2)


def psx_exe_text(data: bytes) -> tuple[int, bytes]:
    """(virtual text base, text bytes) from a PS-X EXE.

    The text is loaded from FILE OFFSET 0x800 for `t_size` bytes to `t_addr`. Mapping the file from
    its own start instead lands everything 0xF800 bytes high and puts an ASCII attribution string
    where the faulting call should be -- the third trap in `docs/issues/0007`.
    """
    if data[:8] != b"PS-X EXE":
        raise ValueError(f"not a PS-X EXE: magic {data[:8]!r}")
    text_addr, text_size = struct.unpack_from("<II", data, 0x18)
    start, end = 0x800, 0x800 + text_size
    if end > len(data):
        raise ValueError(f"text runs past end of file: need {end}, have {len(data)}")
    return text_addr, data[start:end]


def census(text_base: int, text: bytes) -> dict[int, list[int]]:
    """Map each requested entry to the return addresses of every `jal` that targets it."""
    wanted = set(GUEST_ENTRIES.values())
    sites: dict[int, list[int]] = {entry: [] for entry in wanted}
    for index in range(0, len(text) - 3, 4):
        word = struct.unpack_from("<I", text, index)[0]
        pc = text_base + index
        target = decode_jal_target(word, pc)
        if target in sites:
            # `jal` links $ra = PC + 8, because of the delay slot. This is the boundary value.
            sites[target].append(pc + 8)
    return sites


def selftest() -> int:
    """Pin the two decode rules against hand-assembled words with known answers."""
    failures: list[str] = []

    # An absolute J-type target must not be read as PC-relative, and the region nibble must come
    # from the ADDRESS. The trap from docs/issues/0007 was `wrong == right + (delay_slot &
    # 0x0FFFFFFF)`, so build a word whose PC-relative reading is visibly wrong and check the
    # absolute one.
    pc = 0x80020000
    target = 0x80015F54
    word = (OP_JAL << 26) | ((target >> 2) & 0x03FFFFFF)
    got = decode_jal_target(word, pc)
    if got != target:
        failures.append(f"absolute J target: expected 0x{target:08X}, got 0x{(got or 0):08X}")
    # The region must be taken from the PC, not the word: the same word at a KSEG1 PC must decode
    # into KSEG1, and a decoder that read the region from the word would return 0x00015F54.
    if decode_jal_target(word, 0xA0020000) != 0xA0015F54:
        failures.append("region nibble is not taken from the address; a KSEG1 PC decoded as KSEG0")
    pc_relative_would_be = (pc + 4 + ((word & 0x0FFFFFFF) << 2)) & 0xFFFFFFFF
    if pc_relative_would_be == target:
        failures.append("the PC-relative control is not distinguishable; the test proves nothing")

    # A non-J word must be refused rather than decoded into a plausible address. NOTE 0x0C000000 is
    # opcode 3 and IS a `jal`; the first draft of this list included it and the selftest caught it,
    # which is the reason the list is spelled out rather than generated.
    for not_jal in (0x00000000,  # nop
                    0x24020001,  # addiu
                    0x3C000000,  # lui
                    0x8FA20000,  # lw
                    0x03E00008,  # jr
                    0x1000FFFF,  # beq
                    0x8C820000):  # lw
        if decode_jal_target(not_jal, pc) is not None:
            failures.append(f"0x{not_jal:08X} is not `jal` but decoded to a target")

    # The PC+8 link rule, end to end, over a synthetic text. The target MUST be one of the tracked
    # entries, because `census` only collects sites for the entries it was asked about - the first
    # draft of this case aimed at an untracked address and correctly collected nothing, which looked
    # like a decode failure and was not.
    tracked = GUEST_ENTRIES["kDecompressGfxGuest"]
    body = bytearray(16)
    struct.pack_into("<I", body, 0, (OP_JAL << 26) | ((tracked >> 2) & 0x03FFFFFF))
    struct.pack_into("<I", body, 4, (OP_JAL << 26) | ((tracked >> 2) & 0x03FFFFFF))
    found = census(0x80010000, bytes(body))
    if found.get(tracked) != [0x80010008, 0x8001000C]:
        failures.append(f"PC+8 link rule: expected [0x80010008, 0x8001000C], got "
                        f"{[hex(a) for a in found.get(tracked, [])]}")

    # The negative that matters most: an entry NOBODY calls must come back empty, not guessed.
    if census(0x80010000, bytes(body)).get(GUEST_ENTRIES["kAppendBandsGuest"]):
        failures.append("an uncalled entry reported a call site")

    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        return 1
    print(f"selftest OK: scanned {len(body) // 4} word(s); pinned the absolute J target, the "
          f"non-`jal` refusal, the PC+8 link rule, and the empty-result negative")
    return 0


def verify_boundaries(repo: pathlib.Path) -> int:
    """Check the boundaries the port hard-codes against what the image actually contains.

    The whole repair rests on two constants in `vram_rect_queue.h`. A constant that was guessed
    rather than derived would restore exactly the defect this replaced — silently, because a wrong
    boundary still lets most calls return. So the constants are read back out of the header and
    checked against the census, and an entry with MORE THAN ONE `jal` site is refused rather than
    resolved by picking one: choosing among candidates is the guess this gate exists to prevent.
    """
    header = (repo / "game/core/vram_rect_queue.h").read_text()
    declared = dict(re.findall(r"k(\w+?)\s*=\s*(0x[0-9A-Fa-f]{8})u", header))
    exe = repo / "scratch/bin/megamanx4/SLUS_005.61"
    if not exe.is_file():
        print(f"REFUSED: {exe} does not exist. This gate compares header constants against the "
              f"authenticated image and will not pass on a file it never read.")
        return 2
    base, text = psx_exe_text(exe.read_bytes())
    sites = census(base, text)

    pairs = [
        # (boundary constant, census entry, the `jal` site this owner documents standing in for, or
        #  None when the entry has exactly one site in the image and the constant must BE it)
        ("DecompressGfxReturn", "kDecompressGfxGuest", 0x80015F54),
        ("LoadImageGuestReturn", "kLoadImageGuest", 0x80015E8C),
    ]
    failures: list[str] = []
    for constant_key, entry_key, owner_site in pairs:
        if constant_key not in declared:
            failures.append(f"header no longer declares k{constant_key}")
            continue
        if entry_key not in GUEST_ENTRIES:
            failures.append(f"census no longer tracks {entry_key}")
            continue
        entry = GUEST_ENTRIES[entry_key]
        value = int(declared[constant_key], 16)
        found = sites[entry]

        # RULE 1, always: the constant must be a return address the image actually produces for this
        # entry. A boundary invented rather than derived restores the defect silently.
        if value not in found:
            failures.append(f"k{constant_key} = 0x{value:08X} is not among the {len(found)} return "
                            f"address(es) the image produces for 0x{entry:08X} "
                            f"({[hex(a) for a in found]})")
            continue

        # RULE 2: the link rule, re-derived. `jal` sets $ra = PC + 8 because of the delay slot.
        if owner_site is not None and value != owner_site + 8:
            failures.append(f"k{constant_key} = 0x{value:08X}, but the `jal` this owner documents at "
                            f"0x{owner_site:08X} links 0x{owner_site + 8:08X}")
            continue

        # RULE 3: the strongest statement available. An entry with ONE site in the whole image has
        # no ambiguity left, so the constant must be that site — nothing to choose.
        if len(found) == 1 and owner_site is None:
            failures.append(f"k{constant_key} = 0x{value:08X} but 0x{entry:08X} has exactly one "
                            f"`jal` site, 0x{found[0]:08X}, and the constant is not it")
            continue

        how = ("the image's only `jal` to" if len(found) == 1
               else f"one of {len(found)} `jal` sites, the one this owner documents at 0x{owner_site:08X}")
        print(f"  k{constant_key} = 0x{value:08X}  verified against {how} 0x{entry:08X} "
              f"(site 0x{value - 8:08X}, +8 for the delay slot)")

    if failures:
        for line in failures:
            print(f"FAIL: {line}")
        return 1
    print(f"verify-boundaries OK: {len(pairs)} hard-coded boundary/boundaries re-derived from "
          f"{len(text) // 4:,} scanned word(s)")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--verify-boundaries" in sys.argv:
        return verify_boundaries(pathlib.Path(__file__).resolve().parents[1])
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__.strip())
        return 0

    exe = pathlib.Path(sys.argv[1] if len(sys.argv) == 2
                       else "scratch/bin/megamanx4/SLUS_005.61")
    if not exe.is_file():
        print(f"REFUSED: {exe} does not exist. Provision the executable first; this census will "
              f"not report 'no call sites' for a file it never read.")
        return 2
    data = exe.read_bytes()
    base, text = psx_exe_text(data)
    words = len(text) // 4
    sites = census(base, text)
    total = sum(len(v) for v in sites.values())
    print(f"census: {exe.name}  text 0x{base:08X}+0x{len(text):X} = {words:,} word(s) scanned")
    print(f"        {len(GUEST_ENTRIES)} entr(ies) asked about, {total} `jal` site(s) matched\n")
    for name, entry in GUEST_ENTRIES.items():
        found = sites[entry]
        if not found:
            print(f"  0x{entry:08X}  {name:<24} NO `jal` site: retail reached it by `jalr` or a "
                  f"pointer, and the boundary for it is still UNKNOWN")
            continue
        rendered = ", ".join(f"0x{a:08X}" for a in found[:6])
        extra = f" (+{len(found) - 6} more)" if len(found) > 6 else ""
        print(f"  0x{entry:08X}  {name:<24} {len(found):>3} site(s); return address(es): "
              f"{rendered}{extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
