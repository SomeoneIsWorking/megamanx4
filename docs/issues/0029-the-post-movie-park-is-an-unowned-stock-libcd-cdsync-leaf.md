---
id: 29
title: The post-movie park is an UNOWNED stock libcd CdSync leaf, and the whole 6→5→1 chain gates on it
status: open
symptom: Post-movie fields present a flat clear colour; the guest sits at game state 1 / sub-state 2 forever
tags: frame-loop,cd,vsync,widescreen
created: 2026-09-27
updated: 2026-09-27
---

Supersedes the mechanism half of issue 0028. Its wall ("the host must complete the guest's
`CD_cw(0x1B)` read transaction") is CORRECT as a statement of what is missing and WRONG about where
it is missing. This is the second retirement of the same sentence in that issue, and the second
retirement is the one that locates the cause.

## Every address below is read out of the authenticated image

Instrument: `llvm-objdump -d` over `scratch/raw/x4_text.elf`, whose `.text` is
`[0x80010000, 0x8012F800)` — the whole `SLUS_005.61` payload (SHA-1
`213733031136d095ca275d6957695aa25011cfa5`, 1,179,648 B, `PS-X EXE`), so every address quoted is
inside the authenticated image and an image-scoped override can legitimately claim it. Not Ghidra:
its `MIPS:BE:32:default` sleigh decodes this image wrong (RE-02). Where the matching decomp already
has matched C for a function, the decomp is quoted as a LEAD and was checked word-by-word against
these bytes; every one agreed.

## RETIRED, second time: `0x800EDDBC` is not a CD read

Issue 0028 states the per-iteration task "calls `0x800127C8(1)` — which issues `CD_cw(0x1B, 0x7F,
0xFF000000)` at `0x800EDDBC`". Those bytes are:

```
800eddbc: b0 00 0a 24   addiu $10, $zero, 0xb0
800eddc0: 08 00 40 01   jr    $10
800eddc4: 10 00 09 24   addiu $9, $zero, 0x10
```

`jr $10` to `0xB0` with a cause selector in `$9`, in a table of identical stubs at `0x800EDDBC`,
`0x800EDDCC`, `0x800EDDEC`. This is the BIOS exception-vector installer, and the decomp's own
`symbols.us.txt` already says so: **`OpenTh = 0x800EDD9C; ChangeTh = 0x800EDDBC;`** — which is
exactly what this repository's `game/core/bios_threads.h:20` has always called `kChangeThread`. It
issues no CD command.

And `0x800127C8`, which 0028 says issues it, is a task-scheduler stub:

```
800127c8: e8 ff bd 27   addiu $sp, $sp, -0x18
800127cc: 17 80 03 3c   lui   $3, 0x8020
800127d0: 00 83 63 8c   lw    $3, -0x7d00($3)     ; $3 = [0x801F8300], the current-task pointer
800127d4: 01 00 02 24   addiu $2, $zero, 1
800127dc: 02 00 64 a4   sh    $4, 0x2($3)         ; task->arg = a0
800127e0: 00 ff 04 3c   lui   $4, 0xff00
800127e4: 6f b7 03 0c   jal   0xeddbc             ; ChangeTh
800127e8: 00 00 62 a4   sh    $2, 0x0($3)         ; task->status = 1
```

`0x801F8300` is the current-task pointer this repository's `tools/verify_threads.py` already pins, and
`0xFF000000` is `bios_threads::kMainThreadHandle`. It is a yield-to-main stub.

**Also retired, in the same issue text:** "`CdSync` (0x800E5D40)". `0x800E5D40` is
`fast_wait::kCdReady`. The CdSync entry the image actually calls is `0x800E5D20`, and **nothing owned
it** — which is the cause.

## The state machine, recovered

The guest parks in its own XA/BGM machine, and the whole of it is now measured. Its per-field entry
`0x800169D8` (`x4::music_stream::kBeforeObjectsB`) gates on the music-active word and dispatches
through a 4-byte-stride jump table at **`0x800F1AB0`**, indexed by the machine-state word
`D_80139530`:

```
80016a08: 30 95 42 8c   lw    $2, -0x6ad0($2)   ; $2 = [0x80139530]  state
80016a10: 80 10 02 00   sll   $2, $2, 0x2
80016a1c: b0 1a 22 8c   lw    $2, 0x1ab0($1)    ; $2 = [0x800F1AB0 + state*4]
80016a24: 09 f8 40 00   jalr  $2
```

Table read out of the image, and each entry cross-checked against the decomp's function list:

| state | handler | `CdSync` edge | `CdControl` edge | command | next state |
|---|---|---|---|---|---|
| 0 | `0x80016B38` | — | — | — | — |
| 1 | `0x80016B58` | `0x80016B7C` | `0x80016BAC` | `0x1B` `CdlReadS` | raises `D_80173C84`=2 |
| 2 | `0x80016BDC` | — | `CdlPause` loop | `0x09` | 3 |
| 3 | `0x80016C5C` | `0x80016C78` | `0x80016CC4` | `0x1B` `CdlReadS` | 2 |
| 4 | `0x80016D0C` | `0x80016D20` | `CdControlB` `0x800E5FF4` | `0x09` | 0 |
| 5 | `0x80016DAC` | `0x80016DC0` | `0x80016DF0` | `0x15` `CdlSeekL` | 1 |
| 6 | `0x80016E34` | `0x80016E48` | `0x80016E64` | `0x0D` `CdlSetfilter` | 5 |
| 7 | `0x80016E84` | `0x80016E9C` | `0x80016EC4` | `0x0E` `CdlSetmode` | 6 |
| 8+ | `0x8001E400` | — | garbage | — | — |

So the state word is the NEXT command to issue, each handler re-issues its own until it is accepted,
and the forward chain is **7 → 6 → 5 → 1**. Command IDs are the Psy-Q `LIBCD.H` values this image was
linked against (`CdlSetfilter 0x0d`, `CdlSetmode 0x0e`, `CdlSeekL 0x15`, `CdlReadS 0x1b`,
`CdlComplete 0x02`).

**The measured park is state 6.** `D_80139530 == 6` in every post-movie sample, byte-identical over
8,200 presented frames (issue 0028). State 6's handler is `func_80016E34`, and its FIRST act is the
gate that never opens:

```
80016e34: e8 ff bd 27   addiu $sp, $sp, -0x18
80016e3c: 01 00 04 24   addiu $4, $zero, 1
80016e40: 48 97 03 0c   jal   0xe5d20            ; CdSync(1, NULL)      -> ra 0x80016E48
80016e44: 21 28 00 00   move  $5, $zero
80016e48: 02 00 03 24   addiu $3, $zero, 2       ; CdlComplete
80016e4c: 09 00 43 14   bne   $2, $3, 0x80016e74 ; v0 != 2 -> RETURN, state word unchanged
80016e50: 0d 00 04 24   addiu $4, $zero, 0xd
80016e58: e8 5e a5 24   addiu $5, $5, 0x5ee8     ; 0x80175EE8
80016e5c: 64 97 03 0c   jal   0xe5d90            ; CdControl(0x0D,...)  -> ra 0x80016E64
80016e64: 03 00 40 10   beqz  $2, 0x80016e74
80016e68: 05 00 02 24   addiu $2, $zero, 5
80016e70: 30 95 22 ac   sw    $2, -0x6ad0($1)    ; D_80139530 = 5
```

`0x80016E48` is the branch, so the state word can only leave 6 through the CdSync answer. The same
shape is in states 5 and 1 (`80016dc4`, `80016b84`).

## Root cause: the CdSync entry is a hardware poll, and this port has no hardware to poll

`0x800E5D20` is a five-instruction thunk onto the BIOS `CD_sync`:

```
800e5d20: e8 ff bd 27   addiu $sp, $sp, -0x18
800e5d24: 10 00 bf af   sw    $ra, 0x10($sp)
800e5d28: 32 9a 03 0c   jal   0xe68c8            ; CD_sync
800e5d30: 10 00 bf af   lw    $ra, 0x10($sp)
800e5d38: 08 00 e0 03   jr    $ra
```

and `0x800E68C8` opens by calling libetc `VSync` and then polling the CD controller's own status
register — the BIOS's synchronous-looking wait is asynchronous hardware waiting:

```
800e68dc: ff ff 04 24   addiu $4, $zero, -0x1
800e68f4: 6c 93 03 0c   jal   0xe4db0            ; VSync(-1)
800e6910: c0 03 42 24   addiu $2, $2, 0x3c0      ; deadline = field counter + 0x3C0
800e694c: 0b 00 60 14   bnez  $3, 0x800e697c     ; past the deadline -> assert on the string at 0x80011B04
```

`x4::vsync::serveVSync` serves that `VSync(-1)` correctly and cheaply — it is a query of the measured
VBlank counter and returns immediately (`game/core/vsync_sync.cpp:167`). So the wrapper is not what
fails. What fails is that **`VSync(-1)` is not the thing being asked, and this port's CD commands
complete synchronously, so there is no CD controller transition for the status poll to observe.**

Two independent facts establish that nobody owned the entry:

1. **The framework's config-shaped `PlatformHle` has no `cdSync` binding at all.**
   `psxport/runtime/psx/hle/platform_hle.cpp:189` installs `cd_sync_stock_sync` at `plan->cdSyncAddress`
   — but only inside `if (!game->core.cfg)`, the DIRECT-runtime branch. X4 is a config-shaped
   consumer, and the config branch installs `decDctInSync`, `decDctOutSync`, `cdReadSync`,
   `cdDataSync`, `cdInitHandshake`, `gpuTimeoutArm`, `gpuTimeoutCheck`, `drawSync` and
   `changeThread`. There is no `cdSync`. The capability exists in the framework and is simply not
   reachable from this consumer shape.
2. **A whole-image census finds 8 `jal 0x800E5D20` sites and no owner for any of them**:
   `0x80016944`, `0x80016B74`, `0x80016C70`, `0x80016D18`, `0x80016DB8`, `0x80016E40`, `0x80016E94`,
   `0x800188B8`. Six are the state machine's step handlers; state 7's `0x80016E94` never reaches the
   entry because `x4::music_stream::setMode` already calls `cd_sync_stock_sync` directly — which is
   why the run gets as far as state 6 and no further, and why this defect sat one step behind the
   state-7 fix that is already in the tree.

This is not a new idea: the tree already says it. `music_stream.cpp:49` reads
*"The disc controller is already synchronous under the native frame loop, so use its stock-Sony
completion owner directly. Entering the retained wrapper would poll through guest VSync(-1)."* That
was applied to state 7 only.

## The fix, and where it is registered

`game/core/music_cd.{h,cpp}` — a new title owner for the state machine's stock libcd leaf calls:

- **`CdSync` `0x800E5D20`** — a new image-scoped override, registered by
  `music_cd::registerOverrides()` from `native_overrides::install`. It binds the measured edges to the
  framework's existing `cd_sync_stock_sync`, and every caller outside the measured edges keeps the
  original guest body through `guest::callOriginal`.
- **`CdControl` `0x800E5D90`** — the entry already had an owner, so this extends it rather than
  adding a second one: `native_overrides::synchronousCdControl` now asks `music_cd::serveCdControl`
  first and keeps `cd_control_boundary::control` for everything else, including the state-7 Setmode
  edge that the existing owner handles. Completion goes through the framework's `cd_control_sync`,
  whose `0x1B` arm does `xa_stream_start` + `cdc_begin_read` + `stream_active = 1` — which is the
  "request accepted, data delivered, ring/callback side advanced" that issue 0028 asked for.

Scope is the three states on the 6 → 5 → 1 chain, because that is the chain the handshake depends on.
States 2, 3 and 4 are on the pause/reset side, issue `CdControlB` rather than this `CdControl` entry,
and are not required for the handshake. Each owned edge validates the guest's `a0`/`a1`/`a2` against
the literals read out of the image and REFUSES on a mismatch, and the substituted `CdSync` answer is
checked against `CdlComplete` rather than assumed, so the owner can report the other answer.

**No guest byte is written by this owner.** `cd_sync_stock_sync` publishes the libcd result-buffer
contract through `stock_cd_publish_sync`; the machine-state word and the handshake byte are still
written by the guest's own instructions.

Hermetic coverage is `tests/test_x4_music_cd.cpp` (`ctest` `x4_music_cd`, 30/30 green with it), and
it exercises the REAL framework owners rather than stand-ins: every measured edge is served and
accepted, the simulated 6 → 5 → 1 chain advances, four unmeasured callers (including state 7's two
edges) are provably NOT absorbed, and the state-1 published status is asserted to leave the
shell-open bit `0x40` clear, because `func_80016B58` returns before its `CdlReadS` otherwise.

## Falsifier

This closes when a post-movie present contains scene (issue 0028's falsifier), and the intermediate
claim — that the chain now advances — closes earlier and on its own: a run in which
`D_80139530` (`0x80139530`) reaches 2, `D_80173C84` (`0x80173C84`) reaches 2, and
`func_8001DDB0` leaves sub-state 2 (`0x8001DDB0`). If the state word is still 6 with a non-zero
`x4-music-cd` sync tally, the substituted `CdSync` owner is not the thing that was failing and this
issue's mechanism is wrong a third time.

**The run that would produce that evidence was NOT obtained.** The shared product slot
(`$PSX/coord/claims/product-slot`) was held by the operator for a player-blocking Spyro 1 renderer
abort, so no product instance was launched. The owner is therefore statically grounded in the
authenticated bytes and hermetically tested against the shipping framework owners, and **it is not
product-verified.** The measured 4,000-field frontier is unchanged by this change and no new
frontier number is claimed.

## Also measured while here, and still open

- `func_8001DDB0` (sub-state 2) opens with a first half issue 0028 omits: guarded by
  `*(s16*)(state+4) == 0` it calls `func_8001663C(0x20, 0x7F)` once and sets `state->unk4 = 1`
  (`8001ddc8 bnez` / `8001ddd0 jal 0x1663c` / `8001dddc sh`). 0028 quotes only the handshake half and
  gives its addresses as `0x8001DDE0`/`0x8001DEDC`; the real ones are `0x8001DDE4`/`0x8001DDEC`.
- `func_8001663C` is a table dispatcher, not a CD call: it clears `[0x80139568]`, indexes
  `0x80010024 + (a0>>3)*4`, and for `a0 = 0x20` reaches `0x8001670C`, which loads a pointer from
  `[0x800F19F0]`, sets a status byte `0x99` at `0x80139560`, and joins the common tail at
  `0x80016794`. Its callers pass `(0x20,0x7F)`, `(0,0x7F)`, `(0x1C,0x70)` and a per-stage table pair.
  It is on the post-movie path but is NOT the wall, and is not owned here.
- `D_801441B0` has exactly one writer in the whole decomp (`func_80016334`, to 0) and one reader, the
  state-5 `CdlSeekL`/`CdControlF` choice at `0x80016dd8`. It therefore cannot divert state 5 off the
  `CdControl(0x15, …)` edge this owner covers. If it ever were nonzero, state 5 would enter the
  unowned `CdControlF` at `0x800E5EC8` instead, which is a separate, separately-measurable gap.
