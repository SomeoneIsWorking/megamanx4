---
id: C002
kind: claim
status: holds
created: 2026-08-12
tags: overlays,structure
depends: tools/code_scan.py
---

## Claim

Mega Man X4 has NO code overlays: the boot executable SLUS_005.61 is the whole engine, and there is no plain R3000A code anywhere else on the disc

## Evidence

MEASURED 2026-08-12 by tools/code_scan.py, three INDEPENDENT signals, each with a control, over an ENUMERATED denominator. DENOMINATOR: the disc holds 163 files, all enumerated (138 ARC + 11 STR + 11 XA + SLUS_005.61 + SYSTEM.CNF + ZNULL.DAT), 515,298,768 bytes. All 138 .ARC files (26,453,612 B = 25.2 MiB) were extracted and read IN FULL. SIGNAL 1, jr $ra (0x03E00008) at ANY byte alignment: boot exe 5,380 hits (18.24/1k words); 0 of 138 ARC files contain even ONE, across 25.2 MiB; ZNULL.DAT 0. A MIPS function must end in jr $ra, so 25 MiB of code with zero epilogues is impossible. SIGNAL 2, the calibrated code/data window filter imported from external/psxport/tools/exe_similarity.py (recalibrated + selftested 2026-08-12 over 5215 hand-disassembled code windows), best of 4 byte phases: boot exe entry region 99.4% of 16,367 windows; all 138 ARCs median 2.5%, mean 3.5%, max 60.1%; sampled STR 1.0%, XA 0.9%. SIGNAL 3, do j/jal targets land inside .text [0x80010000,0x8012F800)? boot exe 85.0% of 20,428; every ARC <=9.1%, the large ones 0.0-2.1%. THE ONE FILE THAT LIED ON ONE SIGNAL, which is why three were needed: ARC/MOJIPAT.ARC reads 60.1% code-plausible with a 6,292-byte contiguous run, but has 0 jr $ra and 9.1% valid call targets and opens with a 16-entry table of 16-bit offsets — it is a glyph-pattern archive whose bitmap bytes decode as legal instructions. CORROBORATION FROM A SOURCE THAT COULD HAVE SAID OTHERWISE: external/mmx4's config/SLUS_005.61.splat.yaml (155 subsegments) declares exactly ONE code segment (main, start 0x800, vram 0x80010000, bss 0x8012F418+0x46B20) and NOT ONE overlay segment; Vagrant Story's decomp by contrast needs 21 .PRG module configs. WHAT WAS LOOKED FOR THAT WOULD HAVE SHOWN THE OTHER ANSWER AND WAS NOT FOUND: any 'PS-X EXE' magic in any non-boot file (141 files searched, ZERO hits); any .PRG/.OVL/.BIN/.REL-shaped file (the disc has only .ARC/.STR/.XA/.DAT); a CLUSTER of j/jal targets at a fixed base above .text end, which is what an overlay entry table looks like (the 3,073 out-of-.text targets scatter over 386 different 64K pages including impossible addresses like 0x8FFC0000, i.e. misdecoded data words); a large ARC that is mostly code (the largest, PL00_U.ARC at 796,672 B, reads 2.4% plausible / 0 jr $ra / 0.6% valid targets). SCALE CONTRAST measured with the same tool on both binaries: X4 boot .text = 1,177,600 B with 5,380 epilogues; Vagrant Story boot .text = 335,872 B with 972 epilogues PLUS 933,925 B of code in .PRG overlays. NEGATIVE CONTROL: code_scan.py --selftest gates BOTH classes (POSITIVE = 64 KiB at the header-declared entry pc0, must be >=95%, reads 99.4%; NEGATIVE = a media file, must be <=2%, reads 0.9%) and --census refuses (exit 2) on a zero-match glob. BLIND SPOTS, stated because the method cannot see past them: it detects PLAIN R3000A code, so this asserts 'no plain code outside SLUS_005.61', NOT 'no code' — COMPRESSED or packed code inside an .ARC would read as a texture and be indistinguishable from one; code fragments shorter than 64 bytes are invisible by construction; and ~430 MB of .STR/.XA was classified by container format, extension and the boot exe's own path table rather than scanned whole (1 STR chunk of 2.4 MB and 1 XA of 0.8 MB were actually read) — that is the largest unscanned mass on the disc and it is a judgement, not a measurement.

## What would falsify it

a decompressor plus a fixed load base turning up in the boot exe's disassembly (which is what a packed-overlay loader needs), or a j/jal cluster at any fixed base above .text end 0x8012F800, or a full scan of the ~430 MB of STR/XA finding code in it, or the mmx4 pin moving to a config that declares overlay segments
