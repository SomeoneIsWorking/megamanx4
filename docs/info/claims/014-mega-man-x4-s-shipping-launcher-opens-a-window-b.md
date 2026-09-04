---
id: C014
kind: claim
status: holds
created: 2026-08-22
tags:
depends: tools/run.py#run_launcher, tools/test_run.py
reconfirmed: 2026-08-24 23:09:47
verified_at: 2026-08-24 23:09:47
---

## Claim

Mega Man X4's shipping launcher opens a window by default, maps PSXPORT_NOWINDOW=1 only to the headless final sink, honors an explicit asset directory, and does not implicitly enable the diagnostic server.

## Evidence

tools/test_run.py executes the shipping run_launcher through an injected host: seven tests assert default PSXPORT_VK_WINDOW=1, absence of headless/debug-server knobs, explicit NOWINDOW -> PSXPORT_VK_HEADLESS=1 with no window knob, and all provision/build/refusal stages.

## What would falsify it

tools/run.py launch environment changes, tools/test_run.py stops exercising the shipping run_launcher implementation, or a real user launch no longer opens the window by default

## Re-confirmed 2026-08-24 23:07:44

tools/test_run.py executes the shipping run_launcher through an injected host: 13 tests assert default PSXPORT_VK_WINDOW=1, explicit NOWINDOW -> PSXPORT_VK_HEADLESS=1, the locked Python executable passed through provisioning and CMake, isolated scratch/build/player configuration with BUILD_TESTING=OFF, a megamanx4_port-only build, no CTest command, and actionable dependency/provision/build refusals. The direct frozen bootstrap prepare-only path built the player against clean psxport 9c2e3f1c without launching it.

## Re-confirmed 2026-08-24 23:09:47

On commit a53c255, tools/test_run.py passed 13/13 through the shipping run_launcher implementation: default window, explicit NOWINDOW headless sink, locked Python propagation, isolated scratch/build/player with BUILD_TESTING=OFF, megamanx4_port-only build, no CTest command, and actionable failure paths. Direct frozen bootstrap --prepare-only built against clean psxport 9c2e3f1c without launching.
