#!/usr/bin/env python3
"""extract_exe.py — put this game's boot executable in scratch/, from YOUR disc, and check it.

  python3 tools/extract_exe.py [/path/to/disc.chd]

Extracts SLUS_005.61 (the boot target named in SYSTEM.CNF: `BOOT = cdrom:\\SLUS_005.61;1`, measured
2026-08-12) to scratch/bin/megamanx4/, prints the PS-EXE header it read out of it, and compares its
SHA-1 against the value the sozud/mmx4 decompilation states for its own byte-exact build target.
Nothing extracted is ever committed — scratch/ is gitignored, and the executable is Capcom's.

There is deliberately no code-generation step here: extraction owns the retail executable and
identity only. The gameplay runtime executes those authenticated bytes through psxport's Lightrec
boundary. See docs/re-frontier.md (RE-01, RE-02).

WHAT THE HEADER PRINT IS FOR: entry pc0 / t_addr / t_size / initial sp / gp0 are the INPUTS to RE-01 and
to game/core/game_config.cpp's static_assert. They are printed rather than asserted here because this
tool's job is to report what the bytes say, not to enforce what a comment claims.
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discdump  # noqa: E402
from resolve_disc import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE_ON_DISC = "SLUS_005.61"
OUT_DIR = os.path.join(ROOT, "scratch", "bin", "megamanx4")

# The SHA-1 mmx4 (AGPL-3.0) states for its byte-exact build target, read out of the submodule AT RUN
# TIME rather than copied here — a hardcoded copy would silently stop tracking the reference it claims
# to check. mmx4 states it in check.<variant>.txt as `<sha1>  build/<variant>/main.bin` (its splat yaml
# carries no sha1: key, unlike rood-reverse's, so this is where the number lives).
#
# The known-good value, recorded in docs/references.md as the fallback EXPECTATION and deliberately not
# used as a silent substitute: 213733031136d095ca275d6957695aa25011cfa5.
MMX4 = os.path.join(ROOT, "external", "mmx4")
CHECK_FILES = ("check.us.txt",)


def ref_sha1():
    """(sha1, source_path) from the decomp, or (None, why-not)."""
    if not os.path.isdir(MMX4):
        return None, f"{MMX4} does not exist"
    for name in CHECK_FILES:
        p = os.path.join(MMX4, name)
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8", errors="replace"):
            tok = line.split()
            if tok and len(tok[0]) == 40 and all(c in "0123456789abcdefABCDEF" for c in tok[0]):
                return tok[0].lower(), p
        return None, f"{p} states no 40-hex sha1"
    return None, (f"none of {CHECK_FILES} exists under {MMX4} — its layout may have changed; find the "
                  "file that states its target hash and add it to CHECK_FILES")


def psexe_header(data):
    if data[:8] != b"PS-X EXE":
        return None
    f = struct.unpack("<11I", data[0x10:0x10 + 44])
    keys = ["pc0", "gp0", "t_addr", "t_size", "d_addr", "d_size",
            "b_addr", "b_size", "s_addr", "s_size", "sp_gp"]
    return dict(zip(keys, f))


def main():
    disc = resolve(sys.argv[1] if len(sys.argv) > 1 else None, verbose=True)
    dest = discdump.get(disc, EXE_ON_DISC, OUT_DIR)
    if not dest:
        print(f"[exe] {EXE_ON_DISC} was NOT found on {disc} — is this the right disc? "
              "(USA retail: SLUS-00561)", file=sys.stderr)
        return 2
    data = open(dest, "rb").read()
    got = hashlib.sha1(data).hexdigest()
    print(f"[exe] {dest}  {len(data)} bytes  sha1 {got}")

    hdr = psexe_header(data)
    if not hdr:
        print("[exe] NOT a PS-X EXE — the extracted file is not a PSX executable", file=sys.stderr)
        return 2
    print("[exe] PS-EXE header: entry pc0=0x{pc0:08X} text=0x{t_addr:08X}+0x{t_size:X} "
          "data=0x{d_addr:08X}+0x{d_size:X} bss=0x{b_addr:08X}+0x{b_size:X} "
          "sp=0x{s_addr:08X} gp0=0x{gp0:08X}".format(**hdr))
    if hdr["d_size"] == 0 and hdr["b_size"] == 0:
        print("[exe] note: the header declares NO data and NO bss segment, so this game clears its own "
              "BSS in crt0. That is a fact about the header, not about where the BSS is — RE-01.")

    want, why = ref_sha1()
    if want is None:
        # It must SAY it could not check, not pass quietly. A silent pass here is the whole
        # green-over-nothing failure mode this workspace keeps paying for.
        print(f"[exe] CANNOT CHECK the hash: {why}. This run verified the file's SHAPE only "
              "(PS-X EXE + header) and NOT its identity. "
              "`git submodule update --init external/mmx4` to enable the check. The expectation "
              "recorded in docs/references.md is 213733031136d095ca275d6957695aa25011cfa5 — compare by "
              "hand if you need an answer now; this tool will not substitute it silently.")
        return 0
    if got == want:
        print(f"[exe] MATCH mmx4's target sha1 {want} (from {os.path.relpath(why, ROOT)}) — the decomp's "
              "symbol addresses are OUR addresses, with no translation (docs/references.md). That is a "
              "fact about the SUPPLY; it fills no GameConfig field.")
        return 0
    print(f"[exe] MISMATCH: this disc yields {got}, mmx4 targets {want} (from "
          f"{os.path.relpath(why, ROOT)}). A different region/revision. Its addresses do NOT necessarily "
          "apply — treat every borrowed address as unverified until measured against this executable.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
