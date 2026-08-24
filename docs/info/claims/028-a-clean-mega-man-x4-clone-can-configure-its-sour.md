---
id: C028
kind: claim
status: holds
created: 2026-08-24
tags: build,temporal-gate
depends: cmake/megamanx4_port.cmake
---

## Claim

A clean Mega Man X4 clone can configure its source-only temporal gate without a generated shipping target

## Evidence

Clang CMake configure with PSXPORT_BUILD_PORT=OFF completed and ctest -N registered no_temporal_source_dependency while omitting no_temporal_binary_dependency; issue #20 records the former TARGET_FILE generator-expression failure.

## What would falsify it

A no-substrate or PSXPORT_BUILD_PORT=OFF configure names the absent megamanx4_port target, or a generated shipping build omits the binary-symbol dependency test.
