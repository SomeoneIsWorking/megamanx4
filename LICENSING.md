# Licensing — per component, with how each fact is known

This repo is **AGPL-3.0-or-later** (`LICENSE`, the verbatim GNU AGPL v3 text). It is the only tree in
this workspace that carries a licence file, and that asymmetry is deliberate: X4 is the only tree with
an actual obligation, because it may contain code derived from an AGPL-3.0 decompilation.

| component | where | licence | note |
|---|---|---|---|
| this repo's own code (`game/`, `tools/`, docs) | here | **AGPL-3.0-or-later** | because it will contain code derived from `sozud/mmx4` |
| the X4 decomp | `external/mmx4` (submodule — a gitlink only) | AGPL-3.0 | upstream's own `LICENSE`; we redistribute **zero bytes** of it |
| Sony PSY-Q 4.0 headers bundled inside the decomp | `external/mmx4/include/psy-q-4.0/` | © Sony Corporation, **All Rights Reserved** | not the decomp's to relicense, not ours to copy — see below |
| the framework | `external/psxport` (submodule) | **no LICENSE file exists** | its `README.md` says "provided as-is for research and preservation" |
| beetle-psx backend | `external/psxport/vendor/beetle-psx` | GPL-2.0-**or-later** | 121 "any later version" headers, verified |
| imgui / RmlUi / lucent | `external/psxport/vendor/{imgui,rmlui,lucent}` | MIT | from their own LICENSE files |
| game data | your own disc | Capcom's | never in this repo (`*.chd` gitignored) |

## Why AGPL-3.0-or-later

AGPL-3 §5/§13 obligations attach to a work *derived from* the AGPL work. Once `game/` contains bodies,
structs or field layouts taken from mmx4, this repo's distributable form is an AGPL-3 derivative and the
licence file has to say so, or the repo is simply mislicensed. `-or-later` because upstream's LICENSE is
plain AGPL v3 with no "only" qualifier, and it costs nothing.

**Why the combination is distributable.** A shipped binary would link AGPL-3 game code against
GPL-2-or-later beetle-psx. GPL-2-**only** would have made that undistributable; or-later relicenses to
GPL-3, and AGPL-3 §13 explicitly permits linking with GPL-3 work. MIT vendors impose nothing.

## A file-level marker is worth more than this file

`LICENSE` states the repo's terms; it does not tell a future session *which files are contaminated*.
Every file under `game/` containing mmx4-derived material carries:

```cpp
// SPDX-License-Identifier: AGPL-3.0-or-later
// derived from external/mmx4
```

That is what makes "can this move into psxport?" answerable by reading, and it gives
`tools/check_license_containment.py` a second, independent thing to key on.

## Sony's PSY-Q headers

`external/mmx4/include/psy-q-4.0/` is 49 verbatim Sony PSY-Q 4.0 SDK headers (`LIBGPU.H` opens
`/* $PSLibId: Run-time Library Release 4.0$ */ … (C) Copyright 1993-1995 Sony Corporation … All Rights
Reserved`). sozud's AGPL LICENSE covers sozud's work; it cannot relicense Sony's.

**We redistribute none of it.** A submodule is a gitlink: this repo records a 40-char commit SHA and a
URL, so zero bytes of mmx4 — and therefore zero bytes of Sony's headers — enter this repo's object
database or its history. That is the strongest argument for the submodule over vendoring a copy or a
subtree merge, both of which would put those headers in our history where `tools/go_public.py` would
have to flag them forever.

Treat the subtree as read-only reference documentation, like a PDF of the SDK manual. Do not copy it
into `game/`, and do not vendor it into `psxport` "to make the types line up" — psxport has **no PSY-Q
header story at all**, by design: PSX/BIOS entry points are handled by address-keyed HLE
(`runtime/psx/platform_hle.h`), so the port never needs a Sony declaration.

To keep them off local disk (a local-config matter, not a repo matter):

```sh
git -C external/mmx4 sparse-checkout init --cone
git -C external/mmx4 sparse-checkout set src config tools include/helpers
```

## Open item for the operator, recorded rather than quietly assumed

**`psxport` has no LICENSE file at all.** With no grant the default is all-rights-reserved, while the
tree links GPL-2-or-later beetle-psx — which means any *distributed* binary already needs a
GPL-compatible grant on psxport's own code. This repo's AGPL licence does not create that problem, it
makes it visible. The natural fix is an explicit `LICENSE` on psxport (GPL-2.0-or-later, which is both
compatible with beetle and with AGPL-3 linking), and it is the operator's call, not a game repo's.
Until it exists, the framework's terms are **unstated** — this file says so rather than implying they
are settled.
