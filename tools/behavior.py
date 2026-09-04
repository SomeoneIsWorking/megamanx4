#!/usr/bin/env python3
# behavior.py — the BEHAVIOR-DIFFERENCE map: every INTENTIONAL divergence from the retail game.
#
# WHY THIS EXISTS: the faithful path is meant to preserve retail guest behavior. But the port also
# does things ON PURPOSE that the original PSX game does not — draw natively (pc_render), interpolate
# to 60fps, widen the FOV, collapse multi-step loads (pc_skip), and (planned) change what the game
# actually does (pc_enh: faster transitions, expanded load range). Those are NOT bugs and NOT Job-#1
# divergences — they are sanctioned deviations. This registry is their durable ledger, so a byte diff
# from a comparison run can be triaged instantly: is this an unsanctioned bug, or a known intentional change?
# It is the FOURTH axis of this repo's tracking stack:
#     docs/codemap.md      = WHAT EXISTS, per subsystem
#     docs/issues/         = WHAT HAS BEEN TRIED (catalog.py)
#     docs/re-frontier.md  = WHAT IS REAL RE vs a HACK (re_frontier.py)
#     docs/behavior-map.md = WHAT THIS PORT DELIBERATELY CHANGES  <-- this tool
#
# IN THIS REPO IT IS NOT AN OPTIONAL FOURTH AXIS. Mega Man X4 is an ENHANCEMENT port: all three of its
# deliverables (widescreen, drop-in co-op, scripted-wait collapse) are `class: pc_enh` / `affect: full`,
# i.e. deliberate canon guest-state changes, so `behavior.py check` is the ONLY automated gate that they
# stay force-suppressed under the typed comparison-run role. See ../CLAUDE.md and ../docs/plans/enhancements.md.
#
# THE PRIMARY AXIS IS GUEST-MEMORY AFFECT (`affect`) — how much a deviation touches CANON guest state,
# because that is exactly what governs whether it can coexist with the byte-exact reference:
#   none       — writes NO guest memory; a pure host-side overlay (pc_render, fps60, widescreen, ires).
#                INVARIANT: any guest write is a BUG (the comparison catches it). The overlay reads guest+engine
#                state and draws; it never writes guest RAM.
#   non-canon  — writes guest memory, but only to reach the SAME end-state faster (pc_skip's multi-step
#                collapse). INVARIANT: at every skip-fork rendezvous the canon state byte-matches
#                the retail path; comparison mode runs the faithful branch so the shortcut is off there.
#   full       — DELIBERATELY changes canon guest state — the game does something different (pc_enh:
#                faster transitions, expanded load range). INVARIANT: force-suppressed under
#                the shared typed diagnostic-run gate, so comparisons stay enhancement-free BY CONSTRUCTION.
#                An `affect: full` entry MUST cite that suppression in `guard` or `check` FAILS.
#
# THE LOOP:
#   tools/behavior.py                     # session view: deviations grouped by guest-memory affect
#   tools/behavior.py check               # gate: exit 1 if a canon-affecting change is not comparison-suppressed
#   ... add/land an intentional deviation ...
#   tools/behavior.py set faster-transitions --class pc_enh --affect full --status planned \
#       --flag 'cfg_enh("faster-transitions")' --guard 'force-suppressed in typed comparison runs'
#
# STATUS values:
#   verified     — implemented AND confirmed working (USER-eyeballed for a visual change; measured for
#                  a timing change). For affect!=none, also confirmed comparison mode stays clean when it is off.
#   implemented  — code exists behind its gate; not yet confirmed on real data.
#   planned      — designed / named, not yet implemented.
#   reverted     — tried and removed (kept as a dead-end record so it isn't re-attempted blindly).
#
# ENTRY BLOCK FORMAT in docs/behavior-map.md (one `## ` per deviation; hand-editable OR via `set`):
#   ## <name>
#   - **class:** pc_render | widescreen | fps60 | ires | pc_skip | pc_enh
#   - **affect:** none | non-canon | full        (guest-memory affect — the primary axis)
#   - **status:** verified | implemented | planned | reverted
#   - **flag:** how it's toggled (settings.ini key / cfg_enh("name") / Game::mPcSkip / default)
#   - **original:** what the unmodified retail game does
#   - **altered:** what the port does instead when this is enabled
#   - **guard:** the invariant that keeps Job #1 honest (read-only overlay / rendezvous byte-match /
#                force-suppressed in typed comparison runs). REQUIRED for affect=full.
#   - **owner:** game/.../file.cpp[:line]  (or "-" if unimplemented)
#   - **notes:** rationale / caveats / refs / death condition
import os, re, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "behavior-map.md")
FIELDS = ("class", "affect", "status", "flag", "original", "altered", "guard", "owner", "notes")
AFFECTS = ("none", "non-canon", "full")          # primary axis, ordered safest-first
CLASSES = ("pc_render", "widescreen", "fps60", "ires", "pc_skip", "pc_enh")
STATUSES = ("verified", "implemented", "planned", "reverted")
HEADER = "# Behavior-difference map — every INTENTIONAL divergence from the retail game (managed by tools/behavior.py)\n"

# One-line invariant banner per affect group — regenerated on every render.
AFFECT_BANNER = {
    "none": "**affect: none** — pure host-side overlay, writes NO guest memory. Any guest write is a BUG "
            "(comparison catches it).",
    "non-canon": "**affect: non-canon** — writes guest memory only to reach the SAME end-state faster. "
                 "Must byte-match the retail path at every rendezvous; comparison mode runs the faithful branch.",
    "full": "**affect: full** — DELIBERATELY changes canon guest state. MUST be force-suppressed under "
            "the typed comparison-run role (`guard` required) so byte-compares stay clean by construction.",
}


def parse(text):
    for b in re.split(r"(?m)^## +", text)[1:]:
        title = b.splitlines()[0].strip()
        fields = {}
        for k in FIELDS:
            m = re.search(r"(?im)^\s*[-*]?\s*\*\*%s:\*\*\s*(.*?)\s*$" % re.escape(k), b)
            if m and m.group(1).strip():
                fields[k] = m.group(1).strip()
        yield title, fields


def load(refuse_if_missing=True):
    # FIXED HERE (docs/issues/0002, docs/info/instruments/003). The copy this was taken from did
    # `if not os.path.exists(DOC): return []`, and cmd_check over that empty list then printed
    # "[behavior] ok — 0 deviations, 0 canon-affecting (all comparison-suppressed)" and exited 0 — a certified
    # clean bill of health over a corpus that does not exist. In THIS repo behavior.py check is the only
    # automated gate that the port's three canon-affecting enhancements are force-suppressed under
    # comparison mode, so a green over nothing is the worst possible failure mode.
    #
    # `set` legitimately runs before the map exists (it creates it), which is the one caller that passes
    # refuse_if_missing=False.
    if not os.path.exists(DOC):
        if refuse_if_missing:
            sys.exit(f"[behavior] REFUSING: {DOC} does not exist — there is NO behaviour map, so this "
                     f"run examined ZERO deviations. That is not a clean pass. Create entries with "
                     f"`behavior.py set <name> --class .. --affect ..`.")
        return []
    with open(DOC) as f:
        return list(parse(f.read()))


def _affect_rank(f):
    return AFFECTS.index(f.get("affect")) if f.get("affect") in AFFECTS else len(AFFECTS)


def _class_rank(f):
    return CLASSES.index(f.get("class")) if f.get("class") in CLASSES else len(CLASSES)


def render(entries):
    entries = sorted(entries, key=lambda e: (_affect_rank(e[1]), _class_rank(e[1]), e[0].lower()))
    out = [HEADER,
           "Durable ledger of SANCTIONED deviations from the byte-exact reference. Primary axis = "
           "GUEST-MEMORY AFFECT (how much canon guest state a deviation touches). One `## ` block per",
           "deviation, grouped by affect. `tools/behavior.py` = view · `... <words>` = search · "
           "`... check` = gate (a canon-affecting change must be comparison-suppressed).",
           ""]
    # summary line: counts by affect, then by status
    acount, scount = {}, {}
    for _, f in entries:
        acount[f.get("affect", "?")] = acount.get(f.get("affect", "?"), 0) + 1
        scount[f.get("status", "?")] = scount.get(f.get("status", "?"), 0) + 1
    out.append("**By affect:** " + " · ".join(f"{acount[a]} {a}" for a in AFFECTS if a in acount)
               + ("  |  " + " · ".join(f"{acount[a]} {a}" for a in acount if a not in AFFECTS)
                  if any(a not in AFFECTS for a in acount) else ""))
    out.append("**By status:** " + " · ".join(f"{scount[s]} {s}" for s in STATUSES if s in scount) + "\n")

    last_affect = object()
    for name, f in entries:
        aff = f.get("affect", "?")
        if aff != last_affect:
            out.append("---\n")
            out.append(f"### {AFFECT_BANNER.get(aff, '**affect: ' + aff + '**')}\n")
            last_affect = aff
        out.append(f"## {name}")
        for k in FIELDS:
            if k in f:
                out.append(f"- **{k}:** {f[k]}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def save(entries):
    with open(DOC, "w") as f:
        f.write(render(entries))


def cmd_set(args):
    entries = load(refuse_if_missing=False)      # `set` is what CREATES the map
    d = {k: v for k, v in vars(args).items() if k in FIELDS and v is not None}
    if "affect" in d and d["affect"] not in AFFECTS:
        sys.exit(f"bad affect {d['affect']!r}; expected one of {AFFECTS}")
    if "status" in d and d["status"] not in STATUSES:
        sys.exit(f"bad status {d['status']!r}; expected one of {STATUSES}")
    if "class" in d and d["class"] not in CLASSES:
        print(f"[behavior] note: class {d['class']!r} not in {CLASSES} (allowed, but check the taxonomy)")
    for i, (name, f) in enumerate(entries):
        if name.lower() == args.name.lower():
            f.update(d)
            entries[i] = (name, f)
            break
    else:
        entries.append((args.name, d))
    save(entries)
    print(f"[behavior] set {args.name}: " + ", ".join(f"{k}={v}" for k, v in d.items()))


def _summary(entries):
    for aff in AFFECTS + tuple(sorted({f.get("affect", "?") for _, f in entries} - set(AFFECTS))):
        grp = [(n, f) for n, f in entries if f.get("affect", "?") == aff]
        if not grp:
            continue
        print(f"\naffect: {aff}  ({len(grp)})")
        for n, f in sorted(grp, key=lambda e: (_class_rank(e[1]), e[0].lower())):
            print(f"  {f.get('status','?'):11} {f.get('class','?'):11} {n:30} {f.get('owner','')}")


def cmd_check(args, entries=None):
    entries = load() if entries is None else entries
    # FIXED HERE: refuse on an EMPTY map as well as a missing one. A map that parsed to zero entries is
    # indistinguishable, from the outside, from a map whose entries the parser silently failed to
    # match — and this gate's whole job is to assert something about entries.
    if not entries:
        print(f"[behavior] REFUSING: {DOC} parsed to ZERO deviations. Nothing was checked, so this is "
              "not a pass — either the map is empty or the parser did not match its blocks.",
              file=sys.stderr)
        return 2
    fails, warns = [], []
    for n, f in entries:
        aff = f.get("affect")
        if aff not in AFFECTS:
            fails.append(f"{n}: missing/invalid affect (expected one of {AFFECTS})")
            continue
        if f.get("status") not in STATUSES:
            warns.append(f"{n}: missing/invalid status")
        # THE load-bearing invariant: a canon-affecting change with no comparison suppression breaks
        # Job #1 the moment it's enabled in a compare. Require the guard to name that suppression.
        if aff == "full":
            g = (f.get("guard") or "").lower()
            if not re.search(r"comparison|diagnostic.run|suppress", g):
                fails.append(f"{n}: affect=full but `guard` doesn't cite typed comparison-run suppression "
                             f"— a canon change that is not suppressed breaks Job #1")
        elif aff == "none":
            if not f.get("guard"):
                warns.append(f"{n}: affect=none should state the read-only invariant in `guard`")
        elif aff == "non-canon":
            if not f.get("guard"):
                warns.append(f"{n}: affect=non-canon should cite its rendezvous byte-match in `guard`")
    for w in warns:
        print(f"  ⚠ {w}")
    for x in fails:
        print(f"  ✗ {x}")
    n_full = sum(1 for _, f in entries if f.get("affect") == "full")
    # THE DENOMINATOR IS PRINTED ON EVERY PATH, pass included (fixed here): "ok" with no count reads the
    # same whether it checked three entries or none.
    if fails:
        print(f"[behavior] FAIL — checked {len(entries)} deviations, {n_full} canon-affecting; "
              f"{len(fails)} invariant violation(s).")
        return 1
    print(f"[behavior] ok — checked {len(entries)} deviations, {n_full} canon-affecting (each cites "
          f"typed comparison-run suppression in `guard`), {len(warns)} warning(s). "
          f"BLIND SPOT: this gate reads the MAP, not the code — it cannot see whether the suppression "
          f"`guard` describes is actually implemented at the call site.")
    return 0


def cmd_selftest(_args=None):
    """Feed BOTH classes through cmd_check: an affect=full entry that cites suppression MUST pass, and
    the same entry with that clause removed MUST fail. A gate nobody has watched fail is not a gate."""
    good = [("synthetic-enh", {"class": "pc_enh", "affect": "full", "status": "planned",
                               "flag": "PSXPORT_X4_SELFTEST",
                               "guard": "force-suppressed in typed comparison runs",
                               "owner": "-"})]
    bad = [("synthetic-enh", dict(good[0][1], guard="gated behind a CVar the user sets"))]
    empty = []
    checks = []
    print("[selftest] POSITIVE class — affect=full WITH a suppression-citing guard must PASS (exit 0)")
    checks.append(("affect=full + suppression guard passes", cmd_check(None, good) == 0))
    print("[selftest] NEGATIVE class — the SAME entry with the suppression clause removed must FAIL "
          "(exit 1)")
    checks.append(("affect=full without suppression fails", cmd_check(None, bad) == 1))
    print("[selftest] NEGATIVE class — an EMPTY corpus must REFUSE (exit 2), never report a clean pass")
    checks.append(("empty map refuses", cmd_check(None, empty) == 2))
    bad_names = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    print(f"[selftest] {len(checks)} checks, {len(bad_names)} failed")
    return 1 if bad_names else 0


def cmd_list(args):
    for n, f in sorted(load(), key=lambda e: (_affect_rank(e[1]), _class_rank(e[1]), e[0].lower())):
        if args.affect and f.get("affect") != args.affect:
            continue
        print(f"{f.get('affect','?'):10} {f.get('status','?'):11} {f.get('class','?'):11} "
              f"{n:30} {f.get('owner','')}")


def cmd_search(words):
    ws = [w.lower() for w in words]
    hits = [(n, f) for n, f in load() if all(w in (n + " " + " ".join(f.values())).lower() for w in ws)]
    for n, f in hits:
        print(f"## {n}")
        for k in FIELDS:
            if k in f:
                print(f"   {k}: {f[k]}")
        print()
    if not hits:
        print("(no behavior-map entries match; add one with `behavior.py set <name> ...`)")


SUBCOMMANDS = ("set", "check", "list", "selftest")


def main():
    # Bare-word search: `behavior.py <words>`. argparse subparsers reject an unknown first positional as
    # an "invalid choice" BEFORE any fallback runs, so intercept the search case here — a first arg that
    # is neither a known subcommand nor a flag means "search these words" (the sibling map tools share
    # this convention). Flags (-h/--help) and real subcommands fall through to argparse.
    argv = sys.argv[1:]
    if argv and argv[0] == "--selftest":         # flag spelling, same thing as the subcommand
        sys.exit(cmd_selftest(None))
    if argv and not argv[0].startswith("-") and argv[0] not in SUBCOMMANDS:
        cmd_search(argv)
        return

    ap = argparse.ArgumentParser(description="Behavior-difference map (intentional-divergence ledger).")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("set", help="upsert a deviation")
    s.add_argument("name")
    for k in FIELDS:
        s.add_argument("--" + k)
    s.set_defaults(func=cmd_set)
    sub.add_parser("check", help="gate: exit 1 if a canon-affecting change is not comparison-suppressed"
                   ).set_defaults(func=lambda a: sys.exit(cmd_check(a)))
    sub.add_parser("selftest", help="prove the gate can say BOTH yes and no (and refuse on nothing)"
                   ).set_defaults(func=lambda a: sys.exit(cmd_selftest(a)))
    l = sub.add_parser("list", help="one line per deviation")
    l.add_argument("affect", nargs="?")
    l.set_defaults(func=cmd_list)
    args = ap.parse_args()
    if args.cmd is None:
        # default: read-only summary grouped by guest-memory affect. A bare read must NEVER rewrite the
        # doc — save() re-emits only the known FIELDS, dropping hand-added prose. Only `set` writes.
        ents = load()
        if not ents:
            print("(behavior-map empty — add one with `behavior.py set <name> --class .. --affect ..`)")
        else:
            _summary(ents)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
