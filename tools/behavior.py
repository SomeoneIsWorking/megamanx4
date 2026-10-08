#!/usr/bin/env python3
# behavior.py: ledger of intentional divergences from retail, kept in docs/behavior-map.md.
#
# `affect` is how much a deviation touches canon guest memory:
#   none       writes no guest memory (host-side overlay); any guest write is a bug
#   non-canon  writes guest memory only to reach the same end state faster; byte-matches retail at skip rendezvous
#   full       changes canon guest state; must be force-suppressed in typed comparison runs, and `guard` must say so
#
# Usage: behavior.py [words] | check | set NAME --class C --affect A --status S ... | --selftest
# status: verified | implemented | planned | reverted
#
# Entry format in docs/behavior-map.md, one `## <name>` per deviation:
#   class, affect, status, flag, original, altered, guard (required for affect=full), owner, notes
import os, re, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "behavior-map.md")
FIELDS = ("class", "affect", "status", "flag", "original", "altered", "guard", "owner", "notes")
AFFECTS = ("none", "non-canon", "full")          # primary axis, ordered safest-first
CLASSES = ("pc_render", "widescreen", "fps60", "ires", "pc_skip", "pc_enh")
STATUSES = ("verified", "implemented", "planned", "reverted")
HEADER = "# Behavior-difference map — every INTENTIONAL divergence from the retail game (managed by tools/behavior.py)\n"

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
    # Refuse on a missing map: `check` over an empty list would pass vacuously. Only `set` creates it.
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
    # An empty map is as vacuous as a missing one.
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
        # A canon-affecting change must name its comparison-run suppression.
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
    # Print the count on every path so "ok" is not vacuous.
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
    """Run an affect=full entry through cmd_check with and without its suppression clause; only the first must pass."""
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
    # `behavior.py <words>` searches; argparse would reject an unknown first positional, so intercept it.
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
        # Read-only: save() drops hand-added prose, so only `set` writes.
        ents = load()
        if not ents:
            print("(behavior-map empty — add one with `behavior.py set <name> --class .. --affect ..`)")
        else:
            _summary(ents)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
