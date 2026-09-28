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

`ra = 0x800120EC` places the faulting call in a function whose body is a run of `jal`/`nop` pairs:

    800120D8  lw   $v0,0($s0)
    800120E0  addiu $v0,$v0,1
    800120E4  jal  0x800246E8
    800120E8  sw   $v0,0($s0)          ; delay slot
    800120EC  jal  0x80026870          ; <-- ra points HERE, so the previous call returned to it
    800120F0  nop
    800120F4  jal  0x800EA20C
    800120F8  addu $a0,$zero,$zero     ; delay slot
    800120FC  jal  0x80027F54
    80012100  nop
    80012104  jal  0x8002810C
    80012108  nop
    8001210C  jal  0x800EA20C
    80012110  addu $a0,$zero,$zero     ; delay slot
    80012114  jal  0x8002456C

Decoded from the authenticated `SLUS_005.61` at its PS-X EXE load address `0x80010000`. Never
`llvm-objdump --triple=mips`, which misdecodes this image — that is on record in the workspace map and
it is why the words here were read out of the file rather than out of a disassembler.

The override entry, `0x80012600`, is a real function and not a table slot:

    80012600  addiu $sp,$sp,-32
    80012604  lui   $v0,0x801F
    80012608  ori   $v0,$v0,0x8100     ; 0x1F8100xx — the DMA/IFAREAS window
    8001260C  sw    $s1,0x14($sp)
    80012610  addiu $s1,$zero,127

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

## Note on the instrument

The register dump that produced this was a temporary in-tree probe and has been removed: a diagnostic
labelled TEMPORARY has no business in shipping source, and the finding is reproducible from
`tools/live_play.py` plus the byte offsets recorded here. The **owner** should carry an invocation
count for the table it fills, the way the Crash 1 widescreen owner needs one — a table whose contents
are only ever observed at the moment something faults is a table whose corruption is measured once
and then lost.
