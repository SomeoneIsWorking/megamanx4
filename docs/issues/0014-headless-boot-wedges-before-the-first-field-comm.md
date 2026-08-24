---
id: 14
title: Headless boot wedges before the first field commit unless PSXPORT_FNTRACE covers the boot marker set
status: resolved
symptom: headless run reaches no frame markers; ~100% CPU inside guest GPU-DMA churn (func_80012024 -> 800EA80C -> 800EC2C8 -> 800EC228 -> gp0); paced mode dies on the watchdog frame-progress timeout; unpaced runs forever
tags: boot,fntrace,heisenbug,framework,RE-04,instrument,regression-candidate
created: 2026-08-24
updated: 2026-08-24
---

# Boot wedges without FNTRACE — found while verifying the inherited tree (2026-08-24)

MEASURED on megamanx4 @ inherited dirty tree, framework pin d2266f4b, binary scratch/bin/megamanx4_port:

- WITH `PSXPORT_FNTRACE=8001512C,8001D10C,800182E8,800128B8,8001DAF8`: boot reaches 0x8001512C@f67, 0x8001D10C@f67, 0x800182E8@f67, 0x800128B8@f82, task 0x8001DAF8@f83, ABI violations 0 (scratch/logs/re07-inherited-bootgate2.log) — exactly the recorded claim-020/021 numbers. 4/4 runs with this shape passed (paced/unpaced, REPL/no-REPL).
- WITHOUT FNTRACE: execution wedges inside guest main before ANY field commit. 4/4 such runs stalled (scratch/logs/re07-iso-A.log, re07-repl-eof-probe.log, re07-repl-cpu-probe.log, re07-iso-C-paced.log). CPU probe: ~99% of one core executing (not blocked); backtrace sits in gpu_beetle_gp0 -> cfg_on -> note_legacy_read under func_800EC228.
- NOT a flat-out speed race: PSXPORT_NOPACE unset (paced) wedges identically.
- NOT 'any perturbation': `PSXPORT_FNTRACE=800DAE8C` (crt0, pre-boot) still wedges AND its own summary prints 'NEVER CALLED' even though crt0_setup demonstrably executes it — the wrapper displaced the path it probes (re07-iso-D.log). This matches instrument I011's recorded caveat that raw fntrace generated-wrapper probes displace PlatformHle handlers.

SUSPICION (unverified): the traced set includes the BIOS-thread/task functions 0x8001D10C/0x800128B8/0x8001DAF8 — wrapping those perturbs exactly the RE-04 handoff region, and the wedge is real behavior the wrappers accidentally route around.

EVERY recorded evidence log in this repo used FNTRACE over this marker set, which is why nobody saw the wedge. The boot gate therefore currently passes only in the presence of its own instrumentation.

FALSIFIER: a build where headless boot reaches 0x8001512C@~f67 WITHOUT any PSXPORT_FNTRACE falsifies 'the gate depends on its instrumentation'. A run on pin ad5cf802 without FNTRACE reaching f67 would falsify 'introduced by the d2266f4b landing' (attribution currently UNKNOWN — old logs all used FNTRACE too).

NOT FIXED HERE: framework-side investigation is out of this session's scope (framework edits default-none). Registered so the next framework session starts from the repro above.

### Resolution (2026-08-24)
Falsified on the current uninstrumented Clang build at framework pin 7bd24f2b: a bounded 20-second real-disc headless run with no PSXPORT_FNTRACE completed synchronous requests 64, 65, 113, and 51 and remained live until timeout. The exact cause of the older FNTRACE-sensitive run remains historically unattributed.
