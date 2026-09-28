# 0036 — the corruption is a table dispatch through a non-guest word, and it is a CALL not a store

## What was recorded before

`docs/project-state.md` S002 and the workspace map recorded the frontier as "the class-0 interrupt
table entry at `0x8011CB98` holds `0x0113D7D0`, a non-guest word that no owner of the queue could have
written", and left it uncharacterised. The wording implied a *store* went wrong somewhere.

## What the fault actually is

Measured with a register dump at the fault boundary, in a headless driven run
(`tools/live_play.py --budget-frames 6000`, provisioned disc, exit 1):

    FAULT Mega Man X4 guest call: entry 0x80012600 returnPc 0x800120EC guestPc 0x0113D7D0
      detail='ambiguous code-image identity'
      ra=0x800120EC at=0x80200000 v0=0x801F8300 v1=0x00000001
      a0=0x00000000 a1=0xFFFF0000 a2=0x80139554 a3=0x00000000
      t0=0x80166D14 t1=0x0000002A t2=0x000000A0 t3=0x00000000
      s4=0x80141BD8 s5=0x1F800000
    FAULT mem: [0x8011CB90]=00001A2C [0x8011CB98]=800DD7FC [0x801659D0]=00000140
               [0x80141F68]=80165A30 [0x80141BD8]=0002AD8D [0x80173CA0]=44442202

**`guestPc` is `0x0113D7D0` — the same non-guest word that was found sitting in `0x8011CB98`.** The
guest did not store a bad word and then misbehave; **it read that word and dispatched through it.**
The word is an *indirect call target*, not data, and the fault is the CPU jumping to an address
outside every image. The framework's `ambiguous code-image identity` is its honest classification of
"this is not a guest address at all".

**And `0x8011CB98` reads `0x800DD7FC` at the moment of the fault** — a plausible guest address. So the
slot is either written between the read and the dump, or the pointer the guest followed came from a
different slot. That difference matters and is not yet established; it is the next measurement, not a
conclusion.

## The call site, decoded from the image

> **CORRECTED 2026-09-29. The listing below was wrong on 5 of its 7 call targets, and the reason it
> looked right is worth more than the fix. The correct listing is in the replacement section; the
> original is kept so the error is not re-derived.**

Decoded with the framework's own disassembler, `psxport/tools/disasm.py` (Capstone MIPS32, a locked
dependency, gated by `tests/test_disasm.py`), over a RAM dump built from the authenticated
`SLUS_005.61`:

    800120D8  0000028e  lw       $v0, ($s0)
    800120DC  00000000  nop
    800120E0  01004224  addiu    $v0, $v0, 1
    800120E4  8049000c  jal      0x80012600
    800120E8  000002ae  sw       $v0, ($s0)      ; delay slot
    800120EC  e051000c  jal      0x80014780
    800120F0  00000000  nop
    800120F4  83a8030c  jal      0x800ea20c
    800120F8  21200000  move     $a0, $zero      ; delay slot
    800120FC  9557000c  jal      0x80015e54
    80012100  00000000  nop
    80012104  0158000c  jal      0x80016004
    80012108  00000000  nop
    8001210C  83a8030c  jal      0x800ea20c
    80012110  21200000  move     $a0, $zero      ; delay slot
    80012114  1549000c  jal      0x80012454
    scanned 16/16 words; decoded 16/16 words; unknown 0; complete

### What the old listing claimed, and the exact rule that produced it

| `jal` at | claimed | actual | verdict |
|---|---|---|---|
| `0x800120E4` | `0x800246E8` | `0x80012600` | wrong |
| `0x800120EC` | `0x80026870` | `0x80014780` | wrong |
| `0x800120F4` | `0x800EA20C` | `0x800EA20C` | right |
| `0x800120FC` | `0x80027F54` | `0x80015E54` | wrong |
| `0x80012104` | `0x8002810C` | `0x80016004` | wrong |
| `0x8001210C` | `0x800EA20C` | `0x800EA20C` | right |
| `0x80012114` | `0x8002456C` | `0x80012454` | wrong |

**All five wrong entries follow one rule exactly:**

    claimed == actual + (delay_slot_address & 0x0FFFFFFF)

checked for every one of the five, with no exceptions. So the decode treated the J-type 26-bit field
as an offset **from the current PC** instead of applying the MIPS rule

    target = (PC + 4) & 0xF0000000 | (imm26 << 2)

which is the mistake of adding a PC offset that the encoding has already accounted for. The two
entries that came out right are the two whose real target lies in a different 256 MB page, where the
error would have been obvious rather than plausible.

**Why this survived review, and why that is the part to remember:** every wrong number is a *plausible
guest address in the right neighbourhood* — `0x8002xxxx` for a function that is really at
`0x8001xxxx`. A wrong value that looks like the right kind of thing is far more dangerous than a
number that is obviously wrong, and a listing of seven consistent-looking addresses invites the
reader to check the shape rather than the arithmetic.

Independently confirmed by hand for one entry, so the correction does not rest on the tool alone:
the word at `0x800120EC` is `0x0C0051E0`, `op = 3` (`JAL`), `imm26 = 0x000051E0`, `imm26 << 2 =
0x00014780`, and `(PC+4) & 0xF0000000 = 0x80000000`, so the target is **`0x80014780`**.

The override entry, `0x80012600`, is unchanged and was right the first time — it is a real function,
6 of 6 words decoded:

    80012600  e0ffbd27  addiu    $sp, $sp, -0x20
    80012604  1f80023c  lui      $v0, 0x801f
    80012608  00814234  ori      $v0, $v0, 0x8100     ; 0x1F8100xx
    8001260C  1400b1af  sw       $s1, 0x14($sp)
    80012610  7f001124  addiu    $s1, $zero, 0x7f     ; 127
    80012614  1000b0af  sw       $s0, 0x10($sp)

### The return address is CONSISTENT — and I nearly recorded a false anomaly here

An earlier draft of this section claimed a new discrepancy: that `0x80012600` is the callee of the
`jal` at `0x800120E4`, that its return address should therefore be `0x800120E8`, and that the fault's
`returnPc 0x800120EC` "does not belong to this chain". **That was wrong, and it was the same mistake
as the listing above: a convention applied from memory instead of from the architecture.**

A MIPS `jal` sets `GPR[31] = PC + 8`, not `PC + 4`, because the delay slot executes first. So

    jal at 0x800120E4   ->   $ra = 0x800120E4 + 8 = 0x800120EC

**which is exactly the `returnPc` and `ra` the fault reports.** The framework's `returnPc` is "normally
the caller's `$r[31]`" (`psxport/runtime/cpu/native_dispatch.h:76`), so the fault's own numbers are
self-consistent: one static call site, one entry, one return address, all agreeing.

The call surface was also closed rather than assumed:

    static `jal 0x80012600`   1 site   (0x800120E4)
    `jalr` sites in the text  1,005
    image words holding 0x80012600 (a pointer to it)   0

So the entry has exactly one static caller, its `$ra` matches, and the corruption question is
unchanged: the guest dispatched to `0x0113D7D0`, a non-guest word. **There is no new discrepancy
here, and recording one would have sent the next reader after a bug that does not exist.**

### The workspace map's stated reason for hand-decoding was itself wrong

The map records that `llvm-objdump --triple=mips` "misdecodes `SLUS_005.61`". Checked: the string
`0x800120D8` decodes cleanly under the framework's Capstone tool, **16 of 16, zero unknown**. The
real reason llvm-objdump is unusable here is mundane and was never the encoding: it rejects a raw
image outright — *"The file was not recognized as a valid object file"* — because it wants an object
or a recognised container, not a PS-X EXE. The map's claim has been corrected; the instruction it
implied (read words out of the file, do not trust a disassembler) is the right instinct for the wrong
stated reason, and the tool that should have been used was already in the repository.


## What this changes

* The frontier is **not** a queue-overflow residue. Commit 970f346 and issues 0033-0035 bounded the
  VRAM rectangle queue and that work stands; this fault is downstream of it and has its own cause.
* The sentence "a non-guest word that no owner of the queue could have written" was the right
  observation attached to the wrong model. **The word is not a stray write at all — it is the value
  the guest dispatched on.** So the question changes from "which instruction wrote it" to "which
  table slot, and who fills it", which is a different census with a different answer.
* The write census that issue 0035 ran — every instruction that can WRITE the word — was answering a
  question about a store that is not happening.

## The next step, named

1. **Find the slot the guest actually dispatched through.** `$v0 = 0x801F8300` and `$a2 = 0x80139554`
   are live at the fault; read the words at the table bases around `0x8011CB90` and find which one
   holds or held `0x0113D7D0`. Give the scan a denominator.
2. **Decide whether `0x0113D7D0` was ever a plausible value.** Its top half is `0x0113`, which is
   nowhere in guest RAM — so either the table was never initialised for this entry, or it was
   initialised from a count or an index rather than from a pointer. Those are different defects.
3. Recover the function that FILLS the table into readable C++ under `game/`, with the byte evidence,
   following the existing owner style.

1. **Find the slot the guest actually dispatched through.** `$v0 = 0x801F8300` and `$a2 = 0x80139554`
   are live at the fault; read the words at the table bases around `0x8011CB90` and find which one
   holds or held `0x0113D7D0`. Give the scan a denominator.

## Note on the instrument

The register dump that produced this was a temporary in-tree probe and has been removed: a diagnostic
labelled TEMPORARY has no business in shipping source, and the finding is reproducible from
`tools/live_play.py` plus the byte offsets recorded here. The **owner** should carry an invocation
count for the table it fills, the way the Crash 1 widescreen owner needs one — a table whose contents
are only ever observed at the moment something faults is a table whose corruption is measured once
and then lost.
