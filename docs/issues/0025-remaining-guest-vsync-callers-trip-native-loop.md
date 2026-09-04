---
id: 25
title: Remaining guest VSync callers trip native frame ownership
status: open
symptom: Setup, loading, CD, movie, memory-card, or alarm code can reach protected VSync 0x800E4DB0
tags: frame-loop,vsync,timing,RE-09,RE-11
created: 2026-08-27
updated: 2026-09-04
---

## Ownership rule

`X4FrameDriver` owns one complete retail field and replaces only the main loop's `VSync(0)` cadence
call. Full libetc VSync at `0x800E4DB0` is a fail-fast `PlatformHle` ownership trap for every mode.
No caller may restore a successful mode exception or fabricate a counter. Each reached call must be
classified and replaced at the semantic owner: a finite setup/display transition, synchronous CD
transaction, explicit title timing fence, memory-card service, or native alarm/deadline query.

The old offline caller census was deleted with the former execution method. The current discriminator
is runtime-authenticated reach through Lightrec with the full trap armed; it must report both reached
and not-reached owners rather than infer coverage from silence.

## Grounded owners

- `startup_cd` owns finite title setup `0x80013588`, preserving diagnostics, interrupt hook, CD/SPU
  initialization, callback publications, title-state clears, and final call while completing Setmode
  through the native controller.
- `gpu_timeout` replaces alarm `0x800ECB38`'s VSync query with the title field ledger.
- `fast_wait` owns direct/archive CD setup `0x80013968` and `0x80013DA8`; it omits only settling
  waits after the scoped native command has completed.
- `display_init` owns `0x800185F8` and both retail draw-environment publications without its nested
  cadence call.
- `stream_startup` publishes the retail DMA3 callback to table base `0x8011DC5C`, slot
  `0x8011DC68`, preserving the separate generic IRQ-class slot.
- `X4FrameDriver` parks the blocking movie transaction at `UpdateTasks` across host fields. It does
  not restart the gameplay clear while the STR buffer owns the picture.
- `cd_control_boundary` routes only the measured cleanup and BGM Setmode command/return pairs through
  `cd_controller`; all other callers keep their existing owner.
- `movie_cleanup` preserves the cleanup transaction and replaces its three authored fences with
  exactly `1+3+3` host-owned fields.
- `music_stream` preserves BGM state-7's CdSync/Setmode transaction and parks its caller across
  exactly three host fields.

Every native override above calls its authenticated original guest body through the image-keyed
Lightrec dispatcher when it needs the unmodified path; no derived executable body remains in the
repository.

## Retained product evidence

- PID `2710117` published `StDataReadyCallback` `0x800E8188` to DMA3 slot `0x8011DC68`, filled seven
  chunks, armed the final DMA3 interrupt, and dispatched the callback at field 15. PID `2717335`
  measured the ring state chain `3 -> 2 -> 4 -> 0`.
- PID `3087406` completed 90/90 fields with no guest VSync. Presents 30/60/90 were coherent movie
  frames and live pixels covered columns 0..479 in both 24-bit buffers.
- PID `4013759` completed the cleanup at its requested 4,000-field cap with the exact 1+3+3 ledger,
  synchronous mode `0x80`, and no guest VSync. Its images were still authored opening movies, not a
  title or gameplay claim.
- PID `4031142` crossed the second movie cleanup, completed archive requests 113 and 51, then reached
  BGM state 7 at field 2834. It exposed CdSync at return `0x80016E9C` before Setmode; the native
  status owner now covers that exact boundary.
- PID `4086465` exited zero at 4,000/4,000 reconciled fields without a guest-VSync abort, but did not
  reach BGM state 7. Its non-silent WAV is movie XA, not BGM evidence. A same-tree run reached that
  state much earlier; the field-progression difference remains unexplained.

All named PIDs exited and were confirmed absent. These observations predate the native/Lightrec
migration and remain ownership evidence, not current dynamic-execution or gameplay proof.

## Open work and falsifier

State 6/5/1, Setfilter, SeekL, ReadS, GetlocP/Sub-Q, memory-card waits, and any other live VSync caller
remain unverified. The next bounded native/Lightrec run must use the full trap and measure which of
those owners is first reached. This issue closes only when representative front-end/gameplay runs
exercise every classified owner, the runtime reach report has a nonzero denominator, and no guest
VSync entry occurs. A larger blind field cap or absence of an abort is not sufficient.
