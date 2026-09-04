# References — the prior art on this binary, and exactly what we may take from it

The workspace-wide survey is `external/psxport/docs/prior-art.md`. This file is what is specific to
Mega Man X4.

**The standing rule governs everything below: where a reference and a MEASUREMENT disagree, the
measurement wins.** A decomp is an excellent source of function boundaries, names and addresses; it is
not evidence about this port.

## `sozud/mmx4` — an AGPL-3.0 MATCHING decompilation of this exact executable

Vendored as `external/mmx4` (submodule, pinned `1922fcd3`).

| fact | value | how we know |
|---|---|---|
| licence | **AGPL-3.0** | `external/mmx4/LICENSE`, and the GitHub API's `license` field |
| target | `SLUS_005.61` (USA) — the same image on our disc | its `check.us.txt` declares sha1 `213733031136d095ca275d6957695aa25011cfa5` for `build/us/main.bin`, which is the sha1 of the image `tools/extract_exe.py` extracts (1,179,648 bytes) |
| kind | *matching* decomp: its source is meant to build to byte-identical objects | its own splat/objdiff pipeline |
| overlays | **declares exactly ONE code segment and no overlays** | `config/SLUS_005.61.splat.yaml`: 155 subsegments, one code segment `main` at vram `0x80010000`, bss `0x8012F418 + 0x46B20` |
| activity | **DORMANT** — last push 2025-08-25 (confirmed at the ref, `refs/heads/main` = `1922fcd3`, not just from the web UI) | `git ls-remote`, and the API's `pushed_at` |
| progress | **18.5% upper bound on matched code** | NOT measured here, and NOT this port's number — see below |

The USER's ruling (2026-08-12) is that licensing is not a constraint on this repo: *"Licensing isn't an
issue, you can use whatever license needed."* So mmx4 may be used for **code and ideas**, and this repo
is AGPL-3.0-or-later as a result (`LICENSE`, `LICENSING.md`).

**Which tool re-checks the identity, and how.** `tools/extract_exe.py` compares the extracted image's
SHA-1 against the value it reads out of `external/mmx4/check.us.txt` **at run time** — never a hardcoded
copy, because a hardcoded copy would silently stop tracking the reference it claims to check. When the
submodule is absent it SAYS it could not check rather than passing quietly.
`tools/verify_decomp_targets.py` is the per-module version: it reads `target_path:` from each
`config/*.splat.yaml` to learn the module's name on the disc, reads the expected hash from
`check.<variant>.txt`, extracts from OUR disc and compares — printing configs discovered / matched /
mismatched / unchecked / extract-failed, plus how many of the disc's code images are covered. It refuses
(exit 2) on a missing submodule or zero configs, and `--selftest` substitutes a wrong hash to prove it
can report a MISMATCH. (Note the layout difference from the sibling tree it was adapted from:
rood-reverse states `sha1:` inside each splat.yaml; mmx4 does not, which is why the hash comes from
`check.*.txt`.)

## Three rules for using it

**1. A borrowed address is a HYPOTHESIS until measured against these bytes.** Where a reference and a
measurement disagree, the measurement wins. Nothing in `game/core/game_config.cpp` is filled in from it
and nothing should be without the disassembly line that justifies it pasted alongside (the shape
`spider1/game/core/game_config.cpp` uses). This repo has a *tempting* supply of addresses sitting there,
which is exactly why the rule is stated twice — here and in `CLAUDE.md`.

**2. THE LICENCE FIREWALL, as a hard engineering rule.** AGPL-derived code may live in THIS repo and may
**never** be copied, moved, or "upstreamed" into `psxport`. The framework is vendored by five ports, so
copyleft landing there pulls Tomba!2, Spyro, Spider-Man and Vagrant Story in with it. A framework
improvement discovered while reading mmx4 must be **re-derived and described, not transplanted**; if a
change genuinely needs a framework hook, add a *generic* seam upstream and keep the X4-specific body
here. Mark every contaminated file with `// SPDX-License-Identifier: AGPL-3.0-or-later` and
`// derived from external/mmx4`. `tools/check_license_containment.py` is the automated half — four
detection classes with Sony-SDK and sibling-tree vocabulary subtracted, a 15-check `--selftest` gating
both directions, and a printed blind-spot list on every run. **Its blind spot is the leak that actually
worries us**: it catches copy-paste, not a developer who internalises the player-object system from
`src/main/*.c` and writes the co-op patch into psxport from memory. The mitigation is procedural, not
automated.

**3. `external/mmx4/include/psy-q-4.0/` is Sony's SDK, not the decomp's to relicense.** 49 verbatim
PSY-Q 4.0 headers, `(C) Copyright 1993-1995 Sony Corporation … All Rights Reserved`. Treat that subtree
as not-ours-to-take whatever the repo's own LICENSE says. We redistribute zero bytes of it — a submodule
is a gitlink, so nothing of mmx4 enters this repo's object database. psxport has **no PSY-Q header story
at all**, by design (address-keyed HLE in `runtime/psx/platform_hle.h`), so there is never a
legitimate reason to lift one. Details and the sparse-checkout recipe: `LICENSING.md`.

## What it does NOT buy

- **A SHA-1 match says nothing about coverage.** It proves the decomp aims at these bytes, not how much
  of them is decompiled. Its 18.5% is an upper bound on `objdiff` object identity; this port's axis is
  SBS byte-exact RAM parity. **Neither implies the other, and quoting one as evidence about the other is
  how a port looks finished while nothing is gated.** Nothing in this repo may cite that percentage as
  this port's progress.
- **It is a PARTIAL and DORMANT supply.** 18.5%, no push since 2025-08-25. Do not plan as though the
  remaining 81.5% is coming.
- **Nothing has been read.** As of 2026-08-12 no AGPL source from it has been read in this repo — only
  its build config (splat yaml, `check.us.txt`, `extract.sh`) and its LICENSE header. The containment
  rule is therefore currently vacuous in the good sense: there is nothing to contain yet.
- **Do not `--recurse-submodules`.** mmx4 declares three nested submodules of its own —
  `tools/maspsx`, `tools/psximager`, `tools/asm-differ` — which are its *build* toolchain. We consume it
  as source-and-symbols and never build it, so adding three more pins is a real cost. Use
  `git submodule update --init external/mmx4`. **The tradeoff, stated:** anyone who ever wants to
  regenerate a symbol map or run `asm-differ` must init those by hand. If that turns out to be a regular
  part of the X4 workflow, revisit this.

## Prior art that is NOT to be engaged with

`external/psxport/docs/prior-art.md` records that **`mstan/psxrecomp` already ships Mega Man X4–X6
ports**. Read it for the SHAPE of solved problems — overlay capture-and-compile, BIOS as oracle, per-game
repo layout — **not for code** (PolyForm Noncommercial would drag a noncommercial term into this repo).
And note the **standing USER decision, 2026-08-12: we are NOT engaging with that community (R.A.I.D.),
and it is not to be proposed again.**
