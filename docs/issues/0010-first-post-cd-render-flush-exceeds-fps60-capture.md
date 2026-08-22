---
id: 10
title: First post-CD render flush exceeds FPS60 capture capacity
status: resolved
symptom: After faithful HookEntryInt CD IRQ2 delivery clears CdInit, the first bounded rebuilt run aborts in Fps60::rq_capture: 65536 captured + 1 this flush > FPS60_RQ_MAX 65536.
tags: render,render-queue,fps60,boot,next-boundary,RE-04
created: 2026-08-21
updated: 2026-08-21
---

The initial backtrace in scratch/logs/re04-unwind-final-runtime.log reached the retail CD callback/result path and then aborted in Fps60::rq_capture -> RenderQueue::flush -> GpuState::gpu_dma2_linked_list -> func_800EC228 -> func_800EC2C8 -> DrawOTag -> gameMain. A callback-focused FNTRACE run failed to reproduce it, but that trace perturbed timing and was discarded as a progress discriminator. The untraced run reproduced it reliably.

Focused OT evidence ruled out the tempting cap increase and malformed-list theories: scratch/raw/re04-f4.ram contains two 12-link ClearOTagR tables whose final node is the retail libgpu sentinel 0x8011E244=0x04FFFFFF. Each guest loop submitted one drawable. The total reached 65,536 only because no host frame fence ever rotated the accumulated captures.

### Resolution (2026-08-21)
Root cause: x4::vsync::deliver_field used raw gpu_present(), which displayed but never called Fps60::frame_commit(), so each valid one-primitive DrawOTag capture accumulated across guest fields until 65,536 + 1 failed. Retail RAM dump proves both 12-link OTs terminate at 0x8011E244=0x04FFFFFF. Replacing the raw present plus separate pacer with the authoritative one-field frame_commit rotates capture state and paces once; the untraced 20-second runtime reaches external timeout with no overflow or watchdog fault.

### Architecture follow-up (2026-08-22)

This resolution fixed the overflow but exposed framework ownership debt: X4 performs no interpolation,
yet the only complete non-temporal capture/present/ledger/pace fence is a method on `Fps60`. Issue #12
tracks the proper neutral extraction. Replacing the call locally would reintroduce the second-renderer
failure this issue ruled out, so #10 remains resolved while #12 stays open.
