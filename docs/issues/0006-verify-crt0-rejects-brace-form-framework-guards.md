---
id: 6
title: verify_crt0 rejects brace-form framework guards
status: resolved
symptom: tools/verify_crt0.py --selftest reports size_guarded/base_guarded absent and fails 3 cases after clang-format expands each guarded store into a braced block
tags: tooling,crt0,instrument,formatting
created: 2026-08-21
updated: 2026-08-21
---

## Root cause

`FW_MECH` and its sabotage selftest recognized only the old single-line guarded-store spelling.
`clang-format` produced the equivalent braced form, so the source-text instrument reported a false
incompatibility and could not apply two negative mutations. Four `GameConfig` sabotage cases had the
same exact-whitespace defect after the first format sweep.

## Resolution

The framework patterns now tolerate whitespace and optional braces. The config mutations use regexes
over semantic field and declaration shapes instead of exact formatting. The real framework passes
15/15 mechanisms; the local selftest passes 26/26, including deleting each guard and observing the
contradiction plus the resident-range refusal; the Tomba!2 cross-selftest passes 29/29.
