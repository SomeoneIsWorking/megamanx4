---
id: 10
title: First post-CD render flush exceeds FPS60 capture capacity
status: investigating
symptom: After faithful HookEntryInt CD IRQ2 delivery clears CdInit, the first bounded rebuilt run aborts in Fps60::rq_capture: 65536 captured + 1 this flush > FPS60_RQ_MAX 65536.
tags: render,render-queue,fps60,boot,next-boundary,RE-04
created: 2026-08-21
updated: 2026-08-21
---

Evidence: scratch/logs/re04-unwind-final-runtime.log. The same rebuilt run reaches 0x800E5194, trapIntr slot 2, CD callback 0x800E7944, invokes sync callback 0x800E5B5C with status 2/result buffer 0x8013BA78, survives the shared runtime's fail-loud B0:17 unwind contract, then aborts in Fps60::rq_capture -> RenderQueue::flush -> GpuState::gpu_dma2_linked_list -> Core::io_write -> func_800EC228 -> func_800EC2C8 -> gen_func_800EA80C -> gen_func_80012024. Root cause is unknown. Do not raise FPS60_RQ_MAX merely because the diagnostic suggests it: first distinguish a malformed/excessive guest ordering-table chain from incorrect capture activation or a legitimate larger flush. This is the next runtime boundary, separate from the completed CD IRQ contract.

### Note (2026-08-21)

The symptom does not reproduce in scratch/logs/re04-pinned-runtime.log after rebuilding against recorded framework pin `9f1bb927`: CD callback 0x800E7944 returns five times with zero ABI violations and the process runs to the external 20-second bound with no watchdog or capture overflow. That framework range also landed a separately proven CDC BFRD request-latch correction, but this run does not prove that defect caused the malformed render flush. Keep this issue investigating until the old failure is reproduced with focused CD-sector/OT capture or the causal framework change is bisected; absence alone is not a resolution.
