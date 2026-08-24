---
id: 20
title: Clean-clone seam configure referenced an absent shipping target
status: resolved
symptom: CMake generation fails without generated/ because no_temporal_dependency names TARGET_FILE:megamanx4_port even though the port target is deliberately absent
tags: build,cmake,clean-clone,temporal-gate
created: 2026-08-24
updated: 2026-08-24
---

## Root cause

The normal CTest block registered the source scan and shipping-binary symbol scan as one test before `megamanx4_port` was declared. On a clean clone without `generated/rec_sources.cmake`, the build intentionally never creates that target, but CMake still evaluates the `$<TARGET_FILE:megamanx4_port>` generator expression and refuses generation. The source-only seam gate was therefore unreachable in exactly the no-substrate configuration it exists to support.

## Fix

Register `no_temporal_source_dependency` unconditionally with `--check --selftest`. Register `no_temporal_binary_dependency` only after the generated substrate permits `add_executable(megamanx4_port ...)`. This preserves the strict linked-symbol closure without making it a prerequisite for configuring a source-only clone.

## Evidence

A Clang configure with `PSXPORT_BUILD_PORT=OFF` completes and `ctest -N` lists the source dependency test but no binary dependency test. A generated build registers both.

## Falsifier

A no-substrate/`PSXPORT_BUILD_PORT=OFF` configure fails because a test names `megamanx4_port`, or a generated shipping build omits the binary dependency test.
