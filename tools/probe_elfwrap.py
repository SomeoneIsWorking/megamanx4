"""Wrap a PSX-EXE text section in a minimal ELF so llvm-objdump can disassemble it.

Maintainer RE probe helper. Zero dependencies; not a product or test path.
"""

from __future__ import annotations

import struct
from pathlib import Path

PSX_EXE_HEADER = 0x800
EH_SIZE = 0x34
SH_ENT_SIZE = 0x28
PT_LOAD = 1
SHT_PROGBITS = 1
SHT_STRTAB = 3
PF_R = 4
PF_X = 1
ET_EXEC = 2
EM_MIPS = 8


def read_text(exe: Path) -> tuple[int, bytes]:
    data = exe.read_bytes()
    t_addr, t_size = struct.unpack_from("<II", data, 0x18)
    return t_addr, data[PSX_EXE_HEADER : PSX_EXE_HEADER + t_size]


def wrap(vaddr: int, text: bytes, out: Path) -> Path:
    shstr = b"\0.text\0.shstrtab\0"
    text_off = 0x1000
    shstr_off = text_off + len(text)
    shstrtab_off = shstr_off
    sh_off = shstrtab_off + len(shstr)

    eh = bytearray(EH_SIZE)
    struct.pack_into("<4sBBBBB7x", eh, 0, b"\x7fELF", 1, 1, 1, 0, 0)
    struct.pack_into(
        "<HHIIIIIHHHHHH",
        eh,
        0x10,
        ET_EXEC,
        EM_MIPS,
        1,  # e_version
        0,  # e_entry
        EH_SIZE,  # e_phoff
        sh_off,
        0x1000,  # e_flags
        EH_SIZE,
        0x20,
        1,  # e_phnum
        SH_ENT_SIZE,
        3,  # e_shnum
        2,  # e_shstrndx
    )

    ph = struct.pack("<IIIIIIII", PT_LOAD, text_off, vaddr, vaddr, len(text), len(text), 5, 0x1000)

    sh0 = bytes(SH_ENT_SIZE)
    sh_text = struct.pack(
        "<IIIIIIIIII",
        1,
        SHT_PROGBITS,
        PF_R | PF_X,
        vaddr,
        text_off,
        len(text),
        0,
        0,
        4,
        0,
    )
    sh_shstr = struct.pack(
        "<IIIIIIIIII",
        shstr.index(b".shstrtab"),
        SHT_STRTAB,
        0,
        0,
        shstrtab_off,
        len(shstr),
        0,
        0,
        1,
        0,
    )

    out.write_bytes(bytes(eh) + ph + b"\0" * (text_off - EH_SIZE - len(ph)) + text + shstr + sh0 + sh_text + sh_shstr)
    return out
