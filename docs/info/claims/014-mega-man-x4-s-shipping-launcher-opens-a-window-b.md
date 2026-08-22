---
id: C014
kind: claim
status: holds
created: 2026-08-22
tags:
depends: tools/run.py#run_launcher
---

## Claim

Mega Man X4's shipping launcher opens a window by default, maps PSXPORT_NOWINDOW=1 only to the headless final sink, honors an explicit asset directory, and does not implicitly enable the diagnostic server.

## Evidence

tools/test_run.py executes the shipping run_launcher through an injected host: seven tests assert default PSXPORT_VK_WINDOW=1, absence of headless/debug-server knobs, explicit NOWINDOW -> PSXPORT_VK_HEADLESS=1 with no window knob, and all provision/build/refusal stages.

## What would falsify it

tools/run.py launch environment changes, tools/test_run.py stops exercising the shipping run_launcher implementation, or a real user launch no longer opens the window by default
