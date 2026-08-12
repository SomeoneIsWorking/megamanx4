---
id: C003
kind: claim
status: holds
created: 2026-08-12
tags: status
depends: game/core/game_config.cpp, docs/re-frontier.md
---

## Claim

this port has NO recompiled substrate and NO RE'd guest address: every GameConfig address field is 0

## Evidence

2026-08-12. game/core/game_config.cpp is all zeros except port facts (discEnvVar, cardEnvVar/cardDefaultPath, paceQuota=1, windowTitle, preserveVramBackdrop=1) plus three static constexpr PS-EXE header values that are deliberately NOT wired into the boot group; generated/ does not exist, so cmake does not configure megamanx4_port at all and says so with a STATUS message naming RE-01/RE-02. tools/re_frontier.py check: 10 entries parsed, 0 re-verified, 0 hack — every entry todo, blocked or skip-by-design. No binary has ever been built or run in this repo. THIS CLAIM EXISTS TO STOP A LATER SESSION READING SCAFFOLDING AS PROGRESS: the tree has a compiling seam, three enhancement CVars, a full registry set and a vendored matching decomp, and none of that is a single RE'd address.

## What would falsify it

any non-zero guest address appearing in game/core/game_config.cpp, or generated/rec_sources.cmake existing, or tools/re_frontier.py reporting a non-zero re-verified count
