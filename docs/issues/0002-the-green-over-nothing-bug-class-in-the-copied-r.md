---
id: 2
title: the green-over-nothing bug class in the COPIED registry tools, and which copies are fixed
status: resolved
symptom: a tool reports a clean pass over a corpus that does not exist
tags: tooling,instrument,diagnostics
created: 2026-08-12
updated: 2026-08-12
---

THE BUG CLASS, stated as the rule that resolves it: **refuse, don't return empty, when the corpus is missing**, and **a negative must print its denominator and its blind spots**. A diagnostic that can print nothing is lying, and `if (found) report()` makes silence the branch nobody writes.

FOUR INSTANCES, in the exact tools this repo copies. Per tool, the defect and whether it is fixed HERE:

* `re_frontier.py` — printed 'OK: no unknown deps, no cycles, every re-verified step cites evidence' over a parse of ZERO entries. Fixed FOUR times across THREE diverged copies (890 / 443 / skill lines) before the engine was hoisted, and two of those copies were still lying on 2026-08-11 — one of them the copy a game's CLAUDE.md told you to run. **Resolved here by not having a copy:** tools/re_frontier.py is a 30-line SHIM onto external/psxport/tools/port/re_frontier.py with NO fallback, on purpose.
* `catalog.py` — printed '(no matches)' and exited 0 over a docs/issues/ that did not exist. **Fixed in vagrant; that fixed copy is the one taken here** (_load_all() takes refuse_if_missing and cmd_search passes it; a genuine zero-hit search prints 'searched N entries in <abs path> for <terms>' plus its blind spot). Verified both ways in this repo — see the verification log in the bootstrap report.
* `go_public.py` — printed 'RESULT: clean ✓ — ready to publish' over an empty history: zero blobs scanned, exit 0. **Fixed in vagrant; that fixed copy is the one taken here** (prints '[go-public] scanning N blob(s) — scope: <scope>' and exits 2 when N is zero).
* `behavior.py` — **NOT FIXED ANYWHERE BEFORE THIS REPO.** Tomba2Engine/tools/behavior.py (the only copy in the workspace) did `if not os.path.exists(DOC): return []`, and cmd_check over that empty list printed '[behavior] ok — 0 deviations, 0 canon-affecting (all SBS-suppressed)' and exited 0 — a certified clean bill of health over a corpus that does not exist. **THAT MATTERS MORE HERE THAN ANYWHERE**: behavior.py check is the ONLY automated gate that this port's three canon-affecting enhancements stay ORACLE/SBS-suppressed. FIXED HERE, three ways: (1) load() refuses non-zero on a missing map (`set` passes refuse_if_missing=False, since it is what creates the map); (2) cmd_check refuses (exit 2) on a map that parses to zero entries; (3) every pass prints its denominator ('checked N deviations, M canon-affecting') and its blind spot, not a bare 'ok'. A --selftest was added that gates all three directions and it passes 3/3.

STILL BROKEN ELSEWHERE, so the hoist argument stays a measurement rather than an opinion: spyro/tools/catalog.py and spyro/tools/go_public.py, and Tomba2Engine/tools/behavior.py. Every tool in this repo except re_frontier.py is a COPY (docs/codemap.md records this as a known cost); switch them to shims as soon as the engines are hoisted into psxport/tools/port/.

**A FIFTH INSTANCE, in a tool written in THIS repo rather than copied — see #3.** `check_license_containment.py` printed `PASS — scanned 0 text files ... 0 hard matches`, exit 0, when its ENUMERATOR returned nothing (an uninitialised submodule directory; a fully git-ignored tree), while its own `--selftest` reported 15/15 because every fixture tree was one the enumerator could see. Same day, same rule, new costume: the refusal was written for the CORPUS side and never for the TARGET side. Take from it that `--selftest` must feed at least one MALFORMED corpus, not only well-formed ones.
