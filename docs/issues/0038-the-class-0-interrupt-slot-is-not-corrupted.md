# 0038 — The class-0 interrupt slot is NOT corrupted: `0x0113D7D0` is a control-transfer PC, and it is never in guest RAM

`docs/issues/0035` §7 and `docs/re-frontier.md` (RE-10, gap) both record the run's stop as *"the
guest's class-0 interrupt table entry at `0x8011CB98` holds the non-guest word `0x0113D7D0`"*.
**That is a misread and this issue retracts it.** The word `0x0113D7D0` is the guest PC of a control
transfer to an address no code image claims, read out of the dispatcher's own fault line — not the
contents of the slot. Nothing in the run ever wrote it there, because it is never there.

This is the fourth instance in this workspace of the same shape (`is3d` in psxport, the `VSync(0)`
census, `OtAttr` on a null-config title, the Spider-Man gate word): a quantity that is confidently
reported without anyone naming its FEEDER. Here the quantity is a memory word read at the top of
`deliverField`, and the number that was published was taken from an adjacent line of the same log.

## 1. What was measured

Headless, real disc, `PSXPORT_NATIVE_FRAMES=200000`, no audio, unpaced, headless Vulkan; the fault
reproduces deterministically at host field **175,501**, ~37 s in.

**Runtime store observation (the authority).** `PSXPORT_WWATCH=8011CB98,8011CB9C` armed for the
whole run. The framework's watchpoint fires from `Core::writeGuestMemory<Value>` for **every**
width — `mem_w8`, `mem_w16`, `mem_w32` all call it, and DMA3's sector fill goes through `mem_w32`
too — so this is a closed census of every store that reached those four bytes, not a grep.
**6 stores, in the whole run, and none of them wrote `0x0113D7D0`:**

| field | value written | guest PC | ra |
|---|---|---|---|
| 1 | `0x00000000` | `0x800E5678` | `0x800E518C` |
| 1 | `0x800E56FC` | `0x800E51BC` | `0x800E51BC` |
| 1 | `0x00000000` | `0x800E5688` | `0x800E518C` |
| 1 | `0x800E56FC` | `0x800E53F0` | `0x800E4FE4` |
| 2 | `0x00000000` | `0x800EDE04` | `0x800DD71C` |
| 2 | `0x800DD7FC` | `pc` reported as `0x000000C0` | `0x800E54C8` |

`0x800E53F0` is `FUN_800E53F0`, the libetc `SetInterrupt` that `game/core/vsync_sync.cpp` already
documents, and `0x800DD7FC` is libsnd's SS-tick handler — the value `SsStart` installs, which
`docs/issues/0015` measured and which `deliverField` deliberately delivers. **The slot's last write
in the run is the correct one, at field 2.**

**The slot's contents at the fault, read in the same process:** `[0x8011CB98] = 0x800DD7FC`. A
field-indexed change detector added to `deliverField` for this investigation logged the slot
changing exactly twice — `0xDEADBEEF → 0x800E56FC` at field 0 and `0x800E56FC → 0x800DD7FC` at field
1 — and never again through field 175,501.

## 2. The RAM census: the value is never in memory at all

A cadence census (every 64th host field, whole 2 MB of guest RAM through `0x80000000`..`0x80200000`)
ran **2,743 sweeps × 524,288 words = 1,438,562,048 words read** through the fault.

* exact `0x0113D7D0`: **0 words, in 0 of 2,743 sweeps**.
* The feeder's proof, which is the part that makes the zero a measurement: the same sweeps searched
  a near-miss family — any word whose low halfword is `0xD7D0` with a high halfword other than the
  image's own `0x8001` — and it **fired 47 times** with real addresses (`0x8017A588`, `0x80194200`,
  `0x80198AA0`, … all in the heap `[0x80175F38,0x801F8000)`). A census that never ran would have
  produced 0 and 0.

Static, from the authenticated image: the word `0x0113D7D0` is **not in the 294,400 loaded words**
either, there is no `lui $r,0x0113` and no `addiu`/`ori …,0xD7D0` anywhere in it. The halfword
`0xD7D0` occurs **exactly once** in the image, at `0x800F2194`, where the full word is `0x8001D7D0` —
a code address in the table of `0x8001Dxxx` function pointers at `0x800F2170..0x800F21C0`.

**So the value is COMPUTED in a register at run time, not read from memory.** It is not a
corrupted pointer table entry and it is not a stale word nobody cleared; it was never anywhere to
be read from.

## 3. What the fault actually is

`guest call 0x80012600 exited fault at 0x0113D7D0 after 0 cycles`. `0x80012600` is the scheduler,
reached from the game's own frame loop at `0x800120E4` (`jal 0x12600`, continuation `0x800120EC`).
The segment before it ended as `BudgetExhausted` carrying `guestPc = 0x0113D7D0`, and the resume
then asked the dispatcher to run code there. The register file at the fault is the scheduler's
outer frame: `r2=0x801F8300` (its cursor), `r31=0x800120EC`, `r9=0x2A`, `r10=0xA0` — the last two
being the BIOS A-vector thunk state `addiu $t2,$zero,0xA0 / jr $t2 / addiu $t1,$zero,0x2A`, so the
CPU was at a BIOS call when its turn budget expired.

This does not contradict `0036`/`0037`; it removes one candidate from their list. `0036` refuted
the dispatch table at `0x801F8300` as the holder by sweeping 250 slots, and `0037` is on the
BIOS-thread resume path. **The one thing that should be removed from both is the idea that any
memory word holds this value** — the RAM census closes that, and it is cheaper than either.

## 4. What ships

`tools/census_irq_slot_writers.py`, registered as ctest `x4_irq_slot_writer_census`. It is the
static half of this issue: one backward walk per `sb`/`sh`/`sw` (12 instructions, straight-line
only) over all **294,400** loaded words / **37,926** store sites, tracking the base register
through `lui`/`ori`/`addiu`/`addu` and through a load of an image word, with `$gp`/`$sp`/`$fp`
seeded from the port's native crt0 (`gp=0x8012F418`, `sp=fp=0x80200000`).

    class A direct stores that can land in [0x8011CB98,0x8011CB9C): 0
    class A stores whose base this walk could not resolve: 25476 of 37926
    class B image words that ARE a pointer into the window: 0 value(s) at 0 site(s)
    class C guest stores into a DMA MADR cell: 2  (0x800E8FC0 -> ch0, 0x800E8FC8 -> ch1)

**The blind spot is the finding, so it is printed rather than buried**: this slot's real writers
are *parameter-driven* and therefore outside class A — `FUN_800E53F0` stores its callback argument
at `0x8011CB98 + 4*class`. That is exactly why the runtime store observation is the authority for
"what wrote this word" and this tool is the corroborating class list. `--selftest` plants one
instruction sequence per class (a `lui/ori/sw` chain into the window, an image word that is a
pointer into it, a third MADR store) and requires all **3 of 3** to be caught, so its zeros are
measurements rather than a census that never looked. It refuses (exit 2) without the authenticated
image.

## 5. Next step, named

Attribute the **register** that becomes `0x0113D7D0`. The value is arithmetic, so the productive
step is a *translation* watch, not a memory watch: the low half `0xD7D0` appears in exactly one
image word (`0x8001D7D0` at `0x800F2194`) and no immediate in the image builds it, so the
instruction that produced it is either a halfword load of that table entry or a shift/or of runtime
data, and both are countable statically against the `jr`/`jalr` sites reachable from the scheduler.
Until that instruction is named, no C++ owner can be written for it — and the honest state of
this issue is **blocked on that attribution, with the memory hypothesis closed**.

## Falsifier

If a single run ever shows `[0x8011CB98] != 0x800DD7FC` at a `deliverField` boundary while
`PSXPORT_WWATCH=8011CB98,8011CB9C` logs no store into that window, this retraction is wrong and
the writer is a host-side write that bypasses `writeGuestMemory` (the only remaining class). The
watchpoint log is the test: it fires on every width, and it fired 6 times in a run that ended in
the fault.
