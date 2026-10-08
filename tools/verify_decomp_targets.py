#!/usr/bin/env python3
"""Check that the mmx4 decomp's declared target SHA-1 matches this disc's bytes, module by module.

  python3 tools/verify_decomp_targets.py [/path/to/disc.chd]
  python3 tools/verify_decomp_targets.py --selftest

Module names come from config/*.splat.yaml `target_path`, hashes from check.<variant>.txt.
Exit: 0 all matched, 1 mismatched/unchecked/extraction failure, 2 the tool could not look.
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

# X4's only code image is the boot executable (docs/codemap.md).
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
            want = "0" * 40
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
    """Feed a case that must produce a MISMATCH."""
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
