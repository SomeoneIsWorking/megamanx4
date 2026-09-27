---
id: 31
title: The input path was never broken — the witness that reported it broken sampled coarser than
  the edge it was watching
status: open
symptom: Issue 0030 recorded "3 of 3 tap(s) produced NO change at all in the guest's own libpad packet
  word" as a defect in the input path, and gated every gameplay claim for this title on it. The path
  is correct. The surface that measured it cannot resolve a four-field edge.
tags: input,front-end,diagnostics,correction
created: 2026-09-28
updated: 2026-09-28
---

Issue 0030's second numbered defect is **retracted, with the evidence that retracts it and the four
instrument defects that produced it.** The input path for SLUS_005.61 delivers an edge into guest
memory, the guest's own router decodes it, and the framework's BIOS-pad gate — the prime suspect named
in the issue — is **open** on this title, 40 of 40 measured edge fields. Nothing in the input path
needed fixing. What needed fixing was the instrument, and it was wrong in four distinct ways, each of
which independently produced a confident false negative.

## 1. The last stage at which the edge is correct: `guest`. It is correct at every stage.

`game/core/input_path.{h,cpp}` is a new read-only observer called from `x4::vsync::deliverField`
immediately before and immediately after `c->game->pad.serviceFrame()`, so it samples **once per
delivered field** rather than once per endpoint poll. It writes nothing. Every host value it prints is
read through a public accessor on the type that owns it.

The stages, and the measured values on every edge field, from a 2026-09-28 run
(`tools/live_play.py --input-path-trace --tap-frames 24`, one Start tap):

| stage | read from | value | correct |
|---|---|---|---|
| `repl` | `Pad::repl_on` / `repl_tap` | `on=1`, `tap=0xFFF7` | yes |
| `resolved` | `Pad::buttons` after `serviceFrame` | `0xFFF7` | yes |
| `gate` | `Hle::biosPadShouldService()` | `true` | yes |
| `guest` | `mem_r16(0x80166D68 + 2)` | `0xFFF7` | yes |

    24 of 2732 observed field(s) consumed a tap count; the gate was open on 24 of them;
    24 reached the guest's own packet word
    STAGE VERDICT: every observed edge field carried the correct mask through all 4 per-field stages
    (repl -> resolved -> gate -> guest), so the LAST STAGE CORRECT is `guest`

An independent run with a 40-field tap over 2832 observed fields, 5664 observer lines, 0 skipped and 0
refused, gave the same answer for 40 of 40 edge fields.

**Denominators.** 3 measured runs. 1 tap each (3 taps total across the runs), 24 / 40 / 4 edge fields,
5,430 / 5,664 / 6,224 observer lines parsed, 8 read-back samples per tap, 3 `press`/`release` hold
windows. `0 skipped, 0 refused` after the selector fix in §3.4.

## 2. The cause, from bytes, and it is NOT the `biosPadShouldService()` gate

**The gate is open. It cannot be the cause on this title.** The three words it tests, read out of the
running product by the observer on every edge field:

    bios_pad_initialized = true
    bios_pad_irq_started = true
    Hle::biosPadShouldService() = true   (24 of 24 edge fields; 40 of 40 in the second run)

The first two are `Hle` members set only by `Hle::dispatchPadBios`, and the guest gets there. Read
from `SLUS_005.61`'s own text (`llvm-objdump` over the bytes `tools/probe_elfwrap.py` extracts —
NOT Ghidra, whose `MIPS:BE:32:default` sleigh decodes this image wrong, see `docs/re-frontier.md`
RE-02):

* `func_8001213C` (+39) calls `InitPAD(&D_80166D68, 0x22, &D_8012F46C, 0x22)` then `StartPAD()`.
* `InitPAD` (`0x800EE0D0`) ends `jal 0x800EE31C` = `InitPAD2`.
* `InitPAD2` (`0x800EE31C`) is `addiu $10,$0,0xB0 ; jr $10 ; addiu $9,$0,0x12` — a `jr 0xB0` BIOS B-call
  with function **0x12** in `$t1`.
* `StartPAD` (`0x800EE15C`) ends `jal 0x800EE32C` = `StartPAD2`, which is the same `jr 0xB0` with
  function **0x13**.

`runtime/cpu/native_dispatch.cpp` maps `physical == 0xB0` to BIOS table `'B'` with
`function = core.r[9] & 0xff`, and `Hle::dispatchPadBios(0x12)` sets `bios_pad_initialized = true`,
`bios_pad_irq_started = false` and `applyPadWorkAreaAction(Enable)`; `0x13` then sets
`bios_pad_irq_started = true`. So the lifecycle the gate describes **is** entered, and
`biosPadShouldService()` returns true by the framework's own definition.

**This is a testable claim about a title that would otherwise be gated off the framework path, and it
came out the other way.** The framework code needs no change on this evidence, and none is proposed.
If a future title turns out to drive its own SIO without entering that lifecycle, the correct fix is
still in psxport and is still "distinguish the two lifecycles" — but X4 is not that title, so this
issue proposes no framework edit.

## 3. The four instrument defects, each of which could have produced the false negative alone

### 3.1 The read-back samples coarser than the edge. THIS IS THE ONE THAT MATTERS.

    12 packet read(s) cost 162 presented frame(s), i.e. 13.5 frame(s) per read
    16 packet read(s) cost 287 presented frames (17.9 frame(s) per read)
    12 packet read(s) cost 117 presented frame(s) (9.8 frame(s) per read)

against a **4-field** tap. `Session::tap`'s own docstring asserted the opposite — "the endpoint services
one command per presented frame, so … reads the guest's own pad words back, once per frame, for longer
than the edge lasts". "At most one command per presented frame" is an upper bound on how *often* the
endpoint is served, not a lower bound on how long a read *takes*. The read-back therefore reported
`0xFFFF` (idle) for a tap that had been delivered, on every run, and `tools/live_play.py` called that
"the edge was NOT delivered into guest memory".

`Session::measure_read_cost()` now measures the ratio before any tap is offered, and the report prints
whether a read **could** land inside the edge it is watching. With a 24-field tap and a 13.5-frame read
the read-back sees the edge, and it does:

    READ-BACK RESOLUTION: … 13.5 frame(s) per read. This run's taps span 24 field(s) each, so a
    read-back COULD land inside the edge it is watching.
    READ-BACK WITNESS: all 1 tap(s) were witnessed as a change in the guest's own libpad packet word
    packet(active-low)=[65527, 65535]      # 65527 == 0xFFF7, the Start mask

**The endpoint is not a bad surface. It is a surface whose resolution has to be stated before its
negatives mean anything.**

### 3.2 The per-field reader compared an `int` member as if it were a `bool`

`Pad::repl_on` is declared `int` and prints `1`; `Hle`'s three `gate(...)` fields are declared `bool` and
print `true`. The first reader tested `== "true"` against both, so every edge field read as "the drive
was not armed" and the first live run published

    STAGE VERDICT: the first stage that disagreed is `repl`, so the LAST STAGE CORRECT is `endpoint`

for a product that had in fact written the tap into the guest's packet buffer. The selftest fixture
spelled both fields the same way, which is why it passed. The fixture is now pinned to the SHIPPING
spelling of each field and both spellings are exercised (`truthy()`).

### 3.3 The observer packed the packet into one word and the reader sliced the wrong half

`Pad::fillBuffer` writes status, pad id, then the ACTIVE LOW button halfword at **+2**. The first
observer emitted the four bytes as one little-endian word and the reader took the LOW halfword, so a
delivered `0xFFF7` read as `0x4100` — the status/id header, i.e. **the same mistake the frontier probe
shipped in issue 0030, in the other direction.** The record now carries the bytes AND the halfword
(`mem_r16` at +2, the guest's own read), and a line whose two disagree is **REFUSED and counted**, never
resolved in favour of either. The framing is `slot0_bytes=0xFFF74100 slot0_buttons=0xFFF7`, so the
status/id pair `0x4100` and the button word `0xFFF7` are both legible in the record itself.

### 3.4 The channel selector matched the framework's config echo

Selecting observer lines by the substring `x4-input-path` also matched the two `[cfg]` lines that print
`PSXPORT_DEBUG=x4-music-cd,x4-input-path`, and reported them as `2 line(s) skipped for not matching this
tool's reader`. The selector is now the log's bracketed **channel tag**, and the selftest pins that a
config echo naming the channel is not an observer record.

### 3.5 Two unguarded call sites lost whole reports

`Session::tap` sat **outside** the route's `try`, and `hold_window` was unguarded in `main`. Both are
long unbroken stretches of endpoint traffic, and this title's `0x26010006` stage-load fault lands at
presented field ~1,180–2,830 — exactly where they run. A product dying there raised out of the tool and
the run printed **no report at all**, losing the census, the legs, the taps and the captures it had
already measured. Both are now inside the guard, and both have a selftest case
(`a product that dies DURING a tap witness…`, `… DURING a hold window…`).

### 3.6 A reader that printed a constant as though it were a field index

The observer's `vbl=` field printed `vsync::kVblankCounter` — the counter's **address** — where the
field index belonged, and the report duly said

    the edge fields span the VBlank field counter [2148654160, 2148654160]

which is `0x8011DC50` spelled out: a constant that reads like a field index. Fixed to
`core.mem_r32(vsync::kVblankCounter)`; a correct run reports `[2199, 2245]` for a 24-field edge.

## 4. Evidence that an edge reaches guest memory, in the guest's OWN words

### 4.1 A tap, 24 fields, from inside the field loop

    vbl=2199 expected=0xFFF7 resolved=0xFFF7 gate=True guest_packet_bytes=0xFFF74100
             guest_packet=0xFFF7 guest_held=0x0000 guest_pressed=0x0000
    vbl=2201 … vbl=2203 … vbl=2205 …            (24 fields; VBlank counter 2199..2245)

**Active-low convention, stated:** the packet word is the host's ACTIVE LOW mask, so idle is `0xFFFF`
and a pressed Start is that word with bit 3 cleared — `0xFFF7`. `slot0_bytes=0xFFF74100` is the same
four bytes little-endian: `00` status, `41` digital-pad id, `F7 FF` the button word.

The guest's own decoded trio moved during the same fields:

    THE GUEST'S OWN DECODED WORDS across those edge fields: held=['0x0000', '0x0800']
    pressed=['0x0000', '0x0800']

`0x0800` is bit 11. The image's own `external/mmx4/include/psy-q-4.0/LIBETC.H:29,34` says
`#define PADh (1<<11)` and `#define PADstart PADh`, and `323C.c:1849` tests
`if (controller_state & PADstart && arg0->unkD == 1)`. **The guest decoded the tap as Start.**

### 4.2 A hold, 1,334 presented frames — idle → pressed → idle in the guest's own words

    input in the guest's own memory, before the press 0,
    while held {'packet': 65503, 'packet_header': '0041', 'held': 8192, 'previous': 8192, 'pressed': 0},
    after the release {'packet': 65535, 'packet_header': '0041', 'held': 0, 'previous': 0, 'pressed': 0}

`65503 == 0xFFDF` is the ACTIVE LOW mask with raw bit 5 clear (raw Right). The guest's own decoded
`held` is `8192 == 0x2000`, bit 13, and `LIBETC.H:17` says `#define PADLright (1<<13)`. `pressed` is `0`
during the hold, which is **correct for a hold**: a press edge happened before the sample and the word
records edges, not level. The post-release sample is taken after a four-read settle, because the
release is only *accepted* at the endpoint when it is issued — an immediate sample still reads the
held state, and labelling that "after the release" claims a moment the guest has not reached.

The raw→guest mapping is now measured on two buttons and it is the Psy-Q low-byte/high-byte exchange:
raw 3 (Start) → guest 11, raw 5 (Right) → guest 13, i.e. **guest_bit = raw_bit + 8 for raw bits 0–7**.
Both sides of it come from the image: the framework's own `dbg_btn` table is the raw layout
(`start = 0x0008`, `up = 0x0010`, `right = 0x0020`) and the guest's `LIBETC.H` is the swapped one.

### 4.3 An independent cross-check, through a DIFFERENT input route

`docs/issues/0017` closed on 2026-08-24 and recorded, from `PSXPORT_FORCE_BUTTONS` rather than from the
live debug endpoint:

    Forced START -> P1 decode products 0x0800 (PADstart, PSY-Q convention); forced Select ->
    P2 trio 0x0100 (PADselect) with correct edge tracking.

`0x0800` is the value §4.1 measured here from a `tap` issued over the endpoint. **Two independent routes
into the same guest word produce the same decoded value**, and that is what rules out the alternative
reading of §4.1 — that the guest word is echoing the mask the host wrote rather than decoding it.

Issue 0017's title claims "Pad service never ran on the guest-driven path". That was about **whether
`Pad::serviceFrame` was reached**, and it was true then; it is still true structurally, and nothing in
this issue changed it. What this issue corrects is the claim that it was not reached *now*: the service
runs on every delivered field, and no surface outside the field loop could tell the difference.

## 5. How far real pad input got the game

**This is not gameplay, and the honest reason is not the input path.**

| screen / state | reached? | denominator |
|---|---|---|
| boot, CAPCOM intro, both authored STR movies | yes | `x4-music-cd` served 3 of 3 `CdSync` edges (states 6, 5, 1) in the runs that lived long enough |
| post-movie XA/BGM machine entered | **yes**, leg 1 | presented frame 1905, after 12 census observations |
| the accept-input state (`unkD == 1`) | **yes** | 2 of 13 census observations, both at `handshake=2` |
| left the measured park: `game_info` 0/0 → **1/10** → **1/13** | **yes** | leg 2 REACHED at presented frame 1905 |
| a stage scene | **NO** | 0 of 2 captures were taken while the guest submitted more than 2 prims |

So real pad input now **drives the front end through the accept-input state and out of the park**,
which is further than the run recorded in issue 0030 reached with input. It still does not reach a
scene, and the blocker is **not input**: the product ends every run at

    [native-dispatch:error] guest address 0x26010006 resolves to zero or multiple active code images
    [x4-thread:error] guest task stopped at 0x26010006 with unexpected fault boundary: ambiguous
                         code-image identity

at presented field **1,178 / 2,383 / 2,830** across three runs — issue 0030's frontier item 1, a
stage-load garbage pointer, still undiagnosed. The player object did not move during the hold window
either, and that is because that run was still in the movie phase (`game_info=0/0`, guest field
counter 7, 0 prims submitted): **there was no player yet to move.** It is not a statement about
whether movement input works, and it is not evidence either way.

**Boot, logos, menus and two authored movies are NOT gameplay, and none of the above is claimed as
it.** S009 stays `missing`, and the honest reason has moved from "input does not reach the guest" to
"the guest faults loading the first stage".

## 6. Gate

`ctest --test-dir build --output-on-failure` → **33/33 passed**, including the clang-format /
`cpp_policy` gate over the new module. `tools/live_play.py --selftest` **79/79**, up from 44, and the
twenty-nine new cases are the ones this issue is about: both stage verdicts, the real shipping boolean
spelling, the byte-slice refusal, the config-echo selector, the log-format drift, the unpaired half-line,
and the two product-death call sites. Full Clang build clean.

## 7. What remains

1. **`0x26010006`.** The stage-load fault. Now the single blocker between this title and a scene, and
   between it and any gameplay claim at all. Needs RE of the post-park stage setup; guessing the address
   is forbidden.
2. **S009.** Unchanged. It needs 1, and once a scene exists it needs a driver that holds directions
   through it and reads the player object moving.
3. **A held-input measurement taken in-game.** §4.2 proves the *path* carries a hold; it does not prove
   the title's movement handler consumes one, because the run that took it was still in the movie. That
   is a separate measurement, blocked on 1.
4. **The endpoint's read cost is load-dependent** (9.8 / 12.7 / 13.5 / 17.9 frames per read over four
   runs). The tool now measures it per run rather than assuming it, so nothing depends on the exact
   value, but a surface whose per-read cost varies by ~2× is worth knowing about.
5. **Issue 0017's title still reads as an open claim** ("Pad service never ran on the guest-driven path").
   It is `resolved` and its evidence is sound; §4.3 records why this issue does not reopen it. A reader
   arriving at 0017 first should read 0031 §4.3 before concluding the pad service is unreachable.
