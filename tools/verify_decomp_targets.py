#!/usr/bin/env python3
"""verify_decomp_targets.py — does the mmx4 decomp target OUR disc's bytes, module by module?

  python3 tools/verify_decomp_targets.py [/path/to/disc.chd]
  python3 tools/verify_decomp_targets.py --selftest        # proves this tool can print a MISMATCH

Why this exists. external/mmx4 (AGPL-3.0) is a MATCHING decompilation: its source is meant to build to
bytes identical to its target. That makes it a supply of native bodies and symbol names for this port —
but ONLY for the exact image it targets. It states the SHA-1 it builds to, so "are those our bytes?" is
a measurement, not a belief. Run it whenever the submodule pin moves; the pin is dormant at 1922fcd3
(2025-08-25) and a moved pin can change the answer.

HOW mmx4's LAYOUT IS READ, because it differs from the sibling tree this tool was adapted from
(rood-reverse states `sha1:` inside each splat.yaml; mmx4 does not):
  * config/*.splat.yaml states `target_path: disks/<variant>/<MODULE>` — that gives the module's name on
    the disc and the variant.
  * check.<variant>.txt states `<sha1>  build/<variant>/main.bin` — that gives the expected hash.
Both halves are required. A config whose check file is missing is REPORTED AND COUNTED as unchecked,
never silently dropped.

WHAT A NEGATIVE PRINTS. Every run prints its denominators: configs discovered, modules extracted,
matched, mismatched, unchecked, extraction failures, and the disc's code images covered vs not. The tool
REFUSES (exit 2) when the submodule is absent or when it discovers ZERO configs — a search of a corpus
that is not there must never look like a clean pass.

BLIND SPOTS, stated because no run of this tool is evidence about them:
  * A SHA-1 match says NOTHING ABOUT COVERAGE. It proves the decomp aims at these bytes, not how much of
    them is decompiled. mmx4's own figure is an 18.5% upper bound and it is `objdiff` object identity,
    a different axis from this port's SBS byte-exact RAM parity.
  * It does not build the decomp, so it does not check that the decomp's source actually PRODUCES that
    hash today. It checks the DECLARED target against our disc.
  * The "code images on the disc" denominator comes from the measured overlay census (X4 has no code
    overlays; the boot exe is the whole engine — docs/codemap.md), not from this tool. If that census is
    ever falsified, this coverage line is wrong in the safe-looking direction.

Exit: 0 all matched · 1 something mismatched, went unchecked, or failed to extract · 2 the tool could
not look.
"""
import argparse
import glob
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discdump  # noqa: E402
from resolve_disc import resolve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, "external", "mmx4")
CONFIG = os.path.join(REF, "config")
OUT = os.path.join(ROOT, "scratch", "raw", "decomp-targets")

# The disc's code images, from the MEASURED overlay census — not a guess and not this tool's finding.
# X4 has exactly one: the boot executable. See docs/codemap.md and docs/info/claims/.
CODE_IMAGES_ON_DISC = {"SLUS_005.61"}


def _sha1_from_check(variant):
    """(sha1, path) out of check.<variant>.txt, or (None, why-not)."""
    p = os.path.join(REF, f"check.{variant}.txt")
    if not os.path.isfile(p):
        return None, f"{os.path.relpath(p, ROOT)} does not exist"
    for line in open(p, encoding="utf-8", errors="replace"):
        tok = line.split()
        if tok and re.fullmatch(r"[0-9a-fA-F]{40}", tok[0]):
            return tok[0].lower(), p
    return None, f"{os.path.relpath(p, ROOT)} states no 40-hex sha1"


def discover():
    """[(module_on_disc, expected_sha1_or_None, why_not, config_path)] from every splat config."""
    if not os.path.isdir(CONFIG):
        print(f"[verify] {CONFIG} does not exist — the mmx4 submodule is not checked out. This run "
              "compared NOTHING. `git submodule update --init external/mmx4`.", file=sys.stderr)
        raise SystemExit(2)
    found = []
    cfgs = sorted(glob.glob(os.path.join(CONFIG, "*.splat.yaml")))
    for cfg in cfgs:
        target = None
        for line in open(cfg, encoding="utf-8", errors="replace"):
            m = re.match(r"\s*target_path:\s*(\S+)", line)
            if m:
                target = m.group(1)
                break
        if not target:
            print(f"[verify] {cfg} states no target_path — SKIPPED (its module cannot be identified)",
                  file=sys.stderr)
            continue
        module = os.path.basename(target)
        variant = os.path.basename(os.path.dirname(target)) or "us"
        sha, why = _sha1_from_check(variant)
        found.append((module, sha, why, cfg))
    if not found:
        print(f"[verify] discovered ZERO usable splat configs under {CONFIG} "
              f"({len(cfgs)} *.splat.yaml files were present). Refusing to report a pass over nothing.",
              file=sys.stderr)
        raise SystemExit(2)
    return sorted(found)


def run(disc, corrupt_first=False):
    targets = discover()
    dd = discdump.find()
    on_disc = {p for p, _lba, _sz in discdump.listing(disc, dd)}
    matched = mismatched = failed = unchecked = 0
    for i, (mod, want, why, cfg) in enumerate(targets):
        if want is None:
            print(f"  {mod:<24} UNCHECKED  no expected hash: {why}")
            unchecked += 1
            continue
        if corrupt_first and i == 0:
            want = "0" * 40      # --selftest: a hash that CANNOT match, to prove the negative fires
        dest = discdump.get(disc, mod, OUT, dd)
        if not dest:
            print(f"  {mod:<24} EXTRACT-FAIL  (not on this disc?)")
            failed += 1
            continue
        got = hashlib.sha1(open(dest, "rb").read()).hexdigest()
        if got == want:
            print(f"  {mod:<24} MATCH     {got}")
            matched += 1
        else:
            print(f"  {mod:<24} MISMATCH  disc={got} decomp={want}   ({os.path.relpath(cfg, ROOT)})")
            mismatched += 1

    covered = {m for m, _s, _w, _c in targets}
    present = CODE_IMAGES_ON_DISC & on_disc
    absent = sorted(CODE_IMAGES_ON_DISC - on_disc)
    uncovered = sorted(present - covered)
    print(f"\n[verify] disc: {disc} ({len(on_disc)} files)")
    print(f"[verify] decomp configs discovered: {len(targets)} · matched {matched} · "
          f"mismatched {mismatched} · unchecked {unchecked} · extract-failed {failed}")
    print(f"[verify] code images on the disc (from the measured overlay census): "
          f"{len(CODE_IMAGES_ON_DISC)} · present on this disc {len(present)} · covered by a config "
          f"{len(present & covered)} · NOT covered: {uncovered or 'none'}"
          + (f" · NOT FOUND on this disc: {absent}" if absent else ""))
    print("[verify] BLIND SPOTS: a SHA-1 match proves the decomp targets these bytes; it says nothing "
          "about how much of them is decompiled (mmx4's own figure is an 18.5% upper bound, on the "
          "objdiff axis, not this port's SBS RAM-parity axis), nothing about whether the decomp still "
          "BUILDS to that hash today (this tool does not build it), and nothing about any disc file that "
          "is data rather than code. The 'code images' denominator is the overlay census's claim "
          "(docs/codemap.md), not this tool's measurement.")
    return 0 if (mismatched == 0 and failed == 0 and unchecked == 0) else 1


def selftest(disc):
    """Feed a case that MUST produce a MISMATCH. A checker nobody has seen fail is not a checker."""
    print("[selftest] running with the FIRST target's expected hash replaced by 40 zeros; "
          "the run must report exactly one MISMATCH and exit 1.")
    rc = run(disc, corrupt_first=True)
    ok = rc == 1
    print(f"[selftest] {'PASS' if ok else 'FAIL'}: exit {rc} (expected 1). This gates the NEGATIVE "
          "direction only — the POSITIVE is the ordinary run, which must report every config MATCH.")
    return 0 if ok else 2


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("disc", nargs="?")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the comparator can report a mismatch (uses the real disc)")
    a = ap.parse_args()
    d = resolve(a.disc, verbose=True)
    sys.exit(selftest(d) if a.selftest else run(d))
