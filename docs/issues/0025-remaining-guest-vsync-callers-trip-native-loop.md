---
id: 25
title: Remaining guest VSync callers trip native frame ownership
status: open
symptom: Setup, loading, CD, movie, memory-card, or alarm code can reach protected VSync 0x800E4DB0
tags: frame-loop,vsync,timing,RE-09,RE-11
created: 2026-08-27
updated: 2026-09-12
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

The 2026-09-12 native/Lightrec product run with the shared BIOS pad callback candidate reached
VSync `0x800E4DB0` in its first frame after archive/direct CD requests 64/65. The configured
`PlatformHle` full-entry trap returned `FrameBoundary`; `x4::guest::call` required a completed
return and aborted. The log records 706 cycles in that call but no caller RA or completed field.
The next discriminator must capture that RA and enclosing guest transaction before assigning its
semantic owner. This run does not establish a safe VSync exception or successful frame continuation.

The next one-field Lightrec probe, after the shared BIOS pad callback landed, authenticated the same
`SLUS_005.61` image (SHA-1 `213733031136d095ca275d6957695aa25011cfa5`). It completed CD requests
64/65, then `guest::call` entered `UpdateTasks` `0x80012600` and returned `FrameBoundary` at full
VSync `0x800E4DB0` before a completed field. A debugger breakpoint at the **trap entry**, before
the exit request or any possible BIOS-thread restoration, measured `ra=0x80012050`, `a0=0`,
`sp=0x801FFFE0`, `pc=0x800E4DB0`; its host stack was directly inside the Lightrec call of
`UpdateTasks`, not a task fiber. The authenticated EXE has 42 direct `jal VSync` instructions, and
the outer main-loop `jal` at `0x80012048` is the one whose return is `0x80012050`. The reached call
is therefore the outer `VSync(0)`, not a movie field call. The native frame driver seeded
`0x800120EC` as `UpdateTasks`' return target. A debugger breakpoint observed Lightrec's block
boundary callback at that exact PC after requests 64/65, but its active optional return marker was
**0**, while the Core RA was `0x800126AC`. The callback correctly continued: `0x800120EC` did not
match the task's stale zero marker, and guest execution reached the outer loop's VSync.

The owner of the stale marker is a direct task-fiber park inside the title's native STR startup.
The follow-up retail GDB discriminator observed exactly one `ChangeTh`, main-to-task handle
`0xFF000001`, then one `Service::yieldToMain()` from
`stream_startup::serviceFields -> startNativeCdStream(lba=12947, readMode=456) -> run` while its
image-keyed native override and nested `LightrecExecutor::executeFunction` remained live. There
was no task-to-main `ChangeTh` before the outer return. The task's `BoundarySession` therefore
remained parked on the Coro host thread with return marker zero while the main host thread resumed
the outer call and crossed `0x800120EC` with that same active marker. The GDB script counted one
`ChangeTh`, one fiber yield, and one outer return crossing before the unchanged 706-cycle VSync
abort. Its synthetic control printed the correct active marker at `0x00050F00`, so the marker
reading was not a silent or always-zero probe. A separate asset-free Clang synthetic had already
shown the same mechanism: nesting that returned before yield passed, but yielding inside the
nested callback crossed the outer return after 249 blocks/503 instructions with zero interpreter
fallback.

The STR startup native `run` must continue after each of several field waits; returning a typed exit
from `awaitField` alone would skip remaining CD, stream, and VLC work. The candidate framework fix
keeps the native Coro continuation and scopes Lightrec boundary state to the executing host thread.
The maintained framework Clang regression parks a task inside a nested native callback, then proves
the main return, the resumed task return, and both register files; it was red before the boundary change and
passes after it. Cancellation and a fresh task also pass. A subsequent negative synthetic proved
the fallback allowance must likewise be per-boundary: the main thread's one admitted fallback cannot
consume the parked task's allowance. It was red on the shared Lightrec-statistics baseline and passes
with per-context admission counting.

One bounded, authentic, **pre-pin** product recheck used the Clang-built `megamanx4_port` against the
first per-thread marker candidate, with `PSXPORT_NATIVE_FRAMES=5`, `PSXPORT_NOAUDIO=1`,
`PSXPORT_NOPACE=1`, `PSXPORT_VK_HEADLESS=1`, `PSXPORT_WATCHDOG=5`, and
`PSXPORT_LIGHTREC_FALLBACK_BLOCK_LIMIT=0`, under a 30-second timeout. It authenticated the same
`SLUS_005.61` image, completed CD requests 64/65, entered 24-bit display mode, and exited 0 with
`frame loop done` in about one second. The earlier outer VSync abort did not recur. The framework
loop at `native_boot.cpp:214` executes five `FrameLoopShell::step` calls under that cap when no REPL
or debug-server branch is active; the product log does **not** print a completed field count, a
reached-return-PC event, or Lightrec JIT/fallback denominators. The zero fallback **limit** was
configured, but actual fallback usage cannot be inferred from a clean exit. The per-boundary
allowance change followed this retail run and has only synthetic evidence so far.

The shipping dispatch order also resolves `PlatformHle` before image-keyed native overrides. X4
registers `movie::fieldBoundary` at the same VSync entry, but the full-entry `PlatformHle` trap
shadows it. The movie test calls `yieldField` directly and does not exercise this dispatch collision;
that separate collision did not cause the measured outer-loop call. Neither replacing the trap with
a successful VSync exception nor treating this `FrameBoundary` as a completed `UpdateTasks` call
preserves the guest continuation. No timing or dispatch policy changed; the temporary title
call-boundary diagnostic was removed after the probe.

## Open work and falsifier

State 6/5/1, Setfilter, SeekL, ReadS, GetlocP/Sub-Q, memory-card waits, and any other live VSync caller
remain unverified. The next bounded native/Lightrec run must prove that the outer `UpdateTasks`
return marker survives the STR-startup task yield, then measure the next reached owner with the
full trap. This issue closes only when representative front-end/gameplay runs
exercise every classified owner, the runtime reach report has a nonzero denominator, and no guest
VSync entry occurs. A larger blind field cap or absence of an abort is not sufficient.
