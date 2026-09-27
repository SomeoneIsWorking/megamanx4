---
id: 28
title: After both STR movies complete the guest waits on a DMA chain completion the host never delivers
status: open
symptom: Post-movie fields present one flat clear colour and the retail task never ends a turn
tags: RE-09,frame-loop,dma,vsync,widescreen
created: 2026-09-27
updated: 2026-09-27
---

## What was measured

With the libetc VSync entry owned end-to-end (`game/core/vsync_sync.h`), one headless unpaced
13,400-field run and one 60,000-field run, both `PSXPORT_VK_HEADLESS=1 PSXPORT_NOAUDIO=1
PSXPORT_NOPACE=1`:

- both movies complete: `0x80018E50` entered at display field **974** (`ra=0x800184C4`, entry-one
  driver) and field **13,153** (`ra=0x800181DC`, indexed driver), `movieCleanup.completedFields()` 7/7
  at both, `cd.stream_active` 1 before each;
- `cd.stream_active` reaches **0** between field 13,000 and 13,500, and the guest's own field counter
  `0x80141BD8` leaves its movie-frozen value 7 and reaches **0x15F (351)** — the gameplay prefix runs;
- the display-mode init's own `GP1(08)` 15-bit 320x240 switch and its `VSync(-1)` at `0x800E68F4`
  are both passed, and `render_width` **428** is the steady state from then on;
- archive CD requests **113** and **51** complete synchronously.

## The wall

The picture is not a gameplay picture. Every post-movie checkpoint measured — 13,500 / 15,000 /
17,000 / 19,900 — is byte-identical and **one flat colour, RGB(8,8,16)**, 572,166/924,480 (61.89%)
"non-black" in the 1284x720 wide sink, because 233,280 of those pixels are the literal-black wide
margins and the rest is the clear colour. The 4:3 leg measures 686,169/691,200 (99.27%) for the same
reason: (8,8,16) is not (0,0,0).

Meanwhile the retail task `0x8001DAF8` never ends a turn again. The place it waits is **not a loop**:
`0x80021858` writes **DPCR** (`0x1F801064`), then walks a 6,144-byte DMA chain at `0x80173CA0`,
polling the guest flag byte **`0x801721D7`** and each node's status byte. That is the guest waiting
for a DMA completion the host has not raised.

`x4::bios_threads`'s `kMaxTurnFields` reporting bound is what makes this visible, and the bound is
NOT a fix: at 8 the line fired at display field ~13,121 and hid the entire post-movie phase; at 512
the same wait ran to display field **47,762** before printing. The bound was raised so the report
could name the wait, and the comment above the constant says so.

## Falsifier

This closes when a post-movie field presents a picture that is not a flat clear colour — i.e. when
`tools/probe_str_loop.py` shows the guest's `0x80141BD8` still advancing AND a captured present has
more than a handful of distinct colours in the centre 320 columns. Until then, "a post-movie gameplay
frame exists" is false, and no widescreen claim about one may be made.

## Why the widescreen pair could not be judged

`external/psxport/tools/port/widescreen_pair.py` REFUSED the pair, verbatim:

    left  margin 162px wide          :   0.0% non-black, 1 colours, 161/161 repeated columns   <- NOT SCENE
    right margin 162px wide          :   0.0% non-black, 1 colours, 161/161 repeated columns   <- NOT SCENE
    REFUSED: a 1284-column capture with a 162-column margin leaves too few ordinary column pairs beside a join to say what this picture's column-to-column variation normally is, so a discontinuity could not be told from the scene's own texture. NOTHING WAS COMPARED at the joins.

Both facts are the same fact: with a flat clear colour in the centre there is no scene for a margin to
continue, so the tool is right to refuse rather than score it. The seven widened cull owners (issue
0019) therefore still have **no product evidence** — not a negative result, an absent measurement.
Their first product evidence needs a post-movie frame with scene in it, which is what this issue is
about.
