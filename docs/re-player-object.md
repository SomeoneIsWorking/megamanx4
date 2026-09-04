# RE-07 — the player-object system, MEASURED (2026-08-24)

Every fact below was verified against BOTH sources: the AGPL reference decomp
(`external/mmx4`, pin `1922fcd3`, whose `check.us.txt` target SHA-1 equals our extracted
`SLUS_005.61` SHA-1 `213733031136d095ca275d6957695aa25011cfa5`, so its addresses need no
translation) AND our own binary bytes — either a raw instruction scan of the extracted
executable or a Ghidra headless decompilation of a resident-code RAM dump
(`scratch/raw/miss_ram.bin`, imported at 0x80000000 through the shared headless Ghidra workflow; output under
`scratch/decomp/x4_*.c`). A fact carried by only one source is labelled as such. Anything
not listed here stays UNKNOWN — a plausible-sounding sentence elsewhere does not stand in
for it.

Method notes and denominators:

- The binary scan matches `lui rt, hi` followed within 4 instructions by an access whose
  immediate equals the low half (`addiu`/`ori` requiring the same `rt`; loads/stores counted
  on any base). **Blind spot:** accesses that reach an address through an already-materialised
  base register plus a different offset are not counted, so each count is a FLOOR, not a total.
- Function boundaries came from the 7,531-entry recovered executable function map used for this
  measurement, via nearest-preceding-entry attribution.
- Ghidra output is unmodified decompiler text; field semantics were then cross-read against
  mmx4's `include/common.h` struct comments. Where the two disagree, the measurement wins and
  mmx4's guess is recorded as a guess.

## 1. The player struct

| fact | value | confirmed how |
|---|---|---|
| Player object address | `0x801418C8` | mmx4 `symbols.us.txt` line `g_Player = 0x801418C8; // type:PlayerObj size:0xE4`; our binary materialises this address 123× across gameplay code (scan floor; e.g. first site `func_8001D460`, densest region `0x8002xxxx–0x8004xxxx`) |
| Struct size | `0xE4` bytes | mmx4 symbol comment; adjacency in our RAM map: next named global `background_objects = 0x801419B0` sits exactly 4 bytes past `0x801418C8+0xE4`. NOT yet proven from code that reads past byte `0xE3` — treat size as high-confidence, not measured-to-the-byte |
| A second PlayerObj exists | `g_Entity = 0x80175D58`, also `0xE4` | mmx4 symbols; our binary materialises it 9× (e.g. `func_80023EC0`-containing `init_objects`, `reset_objects`); both are spawned/reset/cleared as a PAIR by `init_objects`/`reset_objects` (below) |
| `+0x00 active` (u8) | set to 1 by player init | Ghidra `FUN_80035240`: `DAT_801418c8 = 1` |
| `+0x01 id` (u8) | object id for update-table dispatch | mmx4 `BaseObj.id // 0x01`; `update_main_objects` dispatches `main_object_update_funcs[id]` — Ghidra `FUN_80021234` indexes `PTR_FUN_800f24a4[(char)obj[1]]` over stride 0x9C from `0x8013BED0` to `0x8013DC10` |
| `+0x02 character/type` (u8) | X vs Zero selector for the player object | Ghidra `FUN_80035240`: `g_Player+2 = engine_obj_43 (@0x80172203)`; then per-byte branch picks pointer table `0x80119DF0` (=X) vs `0x8011AFF0` (=Zero) into `g_Player+0x30`. Same +2 byte gates `FUN_80024F5C`/`FUN_8002509C` in `FUN_80024E70` |
| `+0x03 on_screen` (u8) | cull flag written by the on-screen pass | Ghidra `is_on_screen FUN_8002B288` / `FUN_8002B3C0` write `*(obj+3)` |
| `+0x04 state` (u8) | state-machine byte read by gameplay | mmx4 (`g_Player.base.state == 3` checks); our binary: stores to +4 exist but none matched the scan pattern — semantics beyond "exists" remain mmx4-sourced |
| `+0x08 x_pos` (s32 s16.16 fixed) | position; INTEGER half at `+0x0A` | Ghidra camera follow `FUN_80027AAC` reads `DAT_801418D2` (= g_Player+0xA halfword) as the follow target; `is_on_screen` subtracts scroll from the `+0x0A` half. mmx4 comment `// 0x8 and 0xA` agrees |
| `+0x0C y_pos` (s32 s16.16 fixed) | integer half at `+0x0E` | same functions read `DAT_801418D6` / use `param+0xe` |
| `+0x14 bg_slot` (s8) | which background layer's scroll converts world→screen; `<0` = screen-space | Ghidra `is_on_screen`: `if (*(char*)(obj+0x14) < 0)` skip subtraction, else index `bg[slot]` |
| `+0x30 anim-table ptr` (ptr) | per-character animation table | Ghidra `FUN_80035240` writes it from the X/Zero tables above (mmx4 names `unk38` nearby; offset measured from OUR decompile) |
| `+0x47 cur_anim`, `+0x48 prev_anim`, `+0x49` (u8s) | animation state consumed by the sprite builder | Ghidra draw pass `FUN_80024334` indexes frame table `*(obj+0x3c) + obj[0x47]*4`; camera mode fn writes `+0x47/+0x48/+0x49`. Offsets agree with mmx4 `cur_anim // 0x47` |
| `+0x5C hp`, `+0x5D max_hp` (s8) | life-gauge source | Ghidra gauge renderer `FUN_800253F0` reads them (mmx4 has no name there — measured from ours alone) |

UNKNOWN (do not fill from imagination): exact semantics of every remaining PlayerObj byte
(`+0x18..0x2F`, `+0x50..0x56`, `+0x68 ptr`, `+0x6E..0xA7`, `+0xB0..0xE3`). mmx4's `common.h`
names many of these `unkNN`; none has been measured against behaviour in THIS repo yet.

## 2. The camera owner

The camera is a 3-entry array of layer structs ("background objects"), base `0x801419B0`,
stride `0x54` — mmx4 symbol `background_objects = 0x801419B0`; count 3 proven by the init loop
in our Ghidra decompile of `FUN_8002771C` (`while (uVar4 < 3)`).

Measured fields of one layer entry (offsets within the 0x54-byte entry):

| off | meaning | evidence |
|---|---|---|
| `+0x03` | enabled flag (init writes 1) | Ghidra `FUN_8002771C` (`pcVar2[-0x4d]`) |
| `+0x04` | camera MODE byte selecting the follow function | Ghidra dispatcher `FUN_80027850`: `(*(PTR_LAB_800f3134)[mode])(&bg[0])` |
| `+0x08/+0x0C` | follow TARGET x/y (s32), copied to +0x14/+0x18 by the reset-mode fn | Ghidra `FUN_80027908` |
| `+0x0A` | **scroll X (s16) — THE camera x** | every consumer subtracts `*(s16*)(0x801419BA + slot*0x54)` from object x-halves (`is_on_screen`, draw pass `FUN_80024334`, 128-site scan floor); follow helpers advance it (`FUN_80027AFC/27AAC`) |
| `+0x0E` | **scroll Y (s16)** | symmetric, 112-site scan floor |
| `+0x30/+0x32` | horizontal dead-zone margins (init 0x60/0xC0→window 160,160? measured values 0x60,0xC0,0xA0,0xA0 written by `FUN_80027908`) | Ghidra `FUN_80027908` + `FUN_80027AAC` compares `player.x − scroll.x` against them |
| `+0x47/+0x48/+0x49` | follow state: step dir/speed caps (+0x48 max forward, +0x49 = −max back) | Ghidra `FUN_80027974/279D8` write `+0x49 = -+0x48`; `FUN_80027AFC/27B70` clamp per-frame advance |
| `+0x50/+0x52` | level bounds max x/y (s16) seeded from `layout_width/layout_height − 1` (`0x80172224` / `0x80173A28`) | Ghidra `FUN_8002771C` |

Camera ownership chain, all measured on our bytes:

1. Stage spine calls **`func_80027850`** (jal sites `0x8001D3AC`, `0x8001FCB4`, `0x800211D8`,
   `0x80022018`). Gate: enable byte `0x801419F4` && pause flag `0x80141984 == 0`.
2. Dispatcher calls `camera_mode_fns[bg[0].mode](&bg[0])` — table **`0x800F3134`**, entries
   `0x80027908, 0x80027974, 0x800279D8, 0x80027DC0, 0x80027DF0, 0x80028070, 0x800280BC,
   0x800280F4` (read from our exe bytes).
3. Mode helpers read the PLAYER position halves (`0x801418D2`/`0x801418D6`), apply
   dead-zone + capped-step follow, then clamp to bounds (`FUN_80027BE4`) — including pushing
   the PLAYER back when the camera hits a wall (`g_Player.x.hi = bound ± 8`), which matches
   mmx4 `323C.c:3402/3413`.
4. Layer 1/2 parallax derives after modes in `FUN_80028690` (called unconditionally);
   screen-edge load triggers live in `FUN_80028E24` (compares scroll vs `+0x16/+0x1A` anchors
   with ±margins, fires `FUN_80028FEC` with direction codes).

UNKNOWN: which stage-load path writes the per-stage bound/dead-zone bytes (candidates seen:
per-stage config table at `0x800F3188+stage*0x14+substage*10` consumed by `FUN_8002771C`);
the exact parallax math inside `FUN_80028690`.

## 3. Input routing

Measured end-to-end on our binary; the router body matches mmx4's `InitPAD` arguments
exactly (RE-06's unique call at `0x80012194`).

| stage | address | evidence |
|---|---|---|
| libpad packet buffer P1 | `0x80166D68`, cap `0x22` | RE-06 measured InitPAD call; referenced at `0x80012180` (materialise), `0x80012328` (router), `0x8001FFD0` (scan floor) |
| libpad packet buffer P2 | `0x8012F46C`, cap `0x22` | same call; referenced at `0x8001218C`, `0x800123A0` |
| **Router** | **`func_80012328`**, called once per gameMain iteration before the scheduler | mmx4 `2824.c` main loop order; our Ghidra decompile of the whole body |
| validity check | `buf[0] == 0xFF || buf[1] != 0x41 ('A')` → buttons treated as 0 (pad absent) | Ghidra `FUN_80012328` |
| button decode | `~(*(u16*)(buf+2))`, then opposite-direction cancellation: masks `0xA000`/`0x5000` cleared when both bits set | same |
| P1 held (u16) | `0x80166C08`; P1 previous `0x80166C0A` | Ghidra `FUN_80012328` shifts cur→prev each call |
| P1 pressed-edge (u16) | **`controller_state = 0x80166C0C`** = `new & (new ^ old)` | mmx4 symbol + our decompile line-for-line |
| P2 held/prev/edge (u16×3) | `0x80166D50` / `0x80166D52` / `0x80166D54` | Ghidra `FUN_80012328` computes all three every frame |
| gameplay consumers | `controller_state` referenced 77× (scan floor) across title/stage/gameplay; P1 held `0x80166C08` by `func_80012454`, `func_800182E8`, character-select `0x80029A48/29BD8`, `func_80035EF0` | owner-attributed scan |
| P2 consumers | **none found outside the router itself** (P2 edge/prev sites attribute only to `func_80012328`'s neighbourhood) | scan floor; BLIND SPOT: base-register-relative accesses are undercounted, so "no other reader" is scan-supported, not exhaustive |

Consequence for co-op (a lead, not a licence): retail already decodes pad 2 to three u16s
every frame; nothing consumes them. The gap between those bytes and a second player object is
the actual co-op work.

## 4. The spawn path

All measured on our binary via Ghidra; caller attribution via a JAL scan against the executable.

1. **Player init/spawn: `func_80035240`.** Sets `active=1`, takes the character byte from
   engine state `engine_obj_43 @ 0x80172203` (writers: `sb` at `0x8001C224` in
   `func_8001C210`, `0x8001C310` in `func_8001C30C`, `0x80021E54` in `func_80021E3C` —
   front-end/selection range; which UI screen owns each is UNVERIFIED), selects the X/Zero
   pointer table into `+0x30`, seeds position/state from stage scratch (`_DAT_1f800014`,
   `_DAT_1f80001c` — populated by `init_objects` from the per-stage tables
   `&DAT_801499C8 + stage*0xA000` etc.), then initialises companion slots
   (`foo_objects @ 0x80141AB0`, back-pointer at their `+0x50`).
   Callers: `jal 0x8001D3C4` in `func_8001D364`, `jal 0x8001FCCC` in `func_8001FC20`.
2. **Stage-load spine: `init_objects = func_80023DB8`** (mmx4 symbol; our decompile):
   fills stage scratch pointers, runs `func_80024E70` (life-gauge/HUD draw incl. boss gauge),
   `func_800241E8` (OT-head setup), then re-inits every object pool with measured strides —
   main 48×0x9C (`0x8013BED0..0x8013DC10`), weapon 16×0x9C, shot 32×0x9C, visual 32×0x70,
   effect 32×0x30, item 32×0x8C, misc 64×0x60, unk 20×0x60, quad 32×0x60 — counts proven by
   the loop bounds in our own decompile, matching pool sizes in mmx4 symbols.
3. **Reset: `reset_objects = func_8002A7D0`** clears `g_Player` and `g_Entity` via
   `FUN_8002A728`, zeroes all pools, plus named singletons.
4. **Allocation: `find_free_main_obj = func_8002AB74`** scans main_objects for `active==0`
   and zeroes selected fields (our decompile; mmx4 symbol agrees).
5. Per-frame update: **`update_main_objects = func_80021234`** walks the pool, dispatching
   `main_object_update_funcs[base.id]` (`table @ 0x800F24A4`), gated by `g_Player+0xBC` cutscene
   hold and pause flag (mmx4 `323C.c` logic visible in our `FUN_80021234` decompile).
6. Character-select spawner `character_select_spawn_objects = 0x800296A8` spawns MISC objects
   (id 0x41) for select-screen icons — front-end only, NOT the gameplay spawn (measured body;
   correcting mmx4's suggestive name).

UNKNOWN: where `engine_obj_stage/substage` (`0x801721CC/CD`) transition on level change and
which state function invokes `init_objects` per stage (the callers of `func_80023DB8` are not
yet attributed); the checkpoint/respawn writer (`engine_obj_checkpoint @ 0x801721DD`).

## 5. What this unlocks, and what it deliberately does NOT do

- `game/core/player_object.h` provides a READ-ONLY typed lens over these guest blocks
  (constants + offsets pinned by static_assert + a hermetic test,
  `tests/test_x4_player_object.cpp`, ctest `x4_player_object`). No guest write, no override,
  no behavior change ships from this step.
- Byte-match gate prerequisite (RE-10): ANY native body transplanted from mmx4 must first
  have a byte-gate proving the substrate body it replaces matches. Nothing here imports one.
- Co-op remains force-suppressed in typed comparison roles (`tools/behavior.py check`); the co-op
  evidence question is still OPEN and unchanged by this doc.
