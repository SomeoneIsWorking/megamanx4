---
id: 7
title: containment selftest writes fixtures to shared tmp
status: resolved
symptom: The containment selftest prints fixture paths under /tmp, violating the workspace scratch-output rule.
tags: tooling,containment,scratch
created: 2026-08-21
updated: 2026-08-21
---

## Root cause

`_tmpdir()` relied on `tempfile.TemporaryDirectory` without an explicit directory. A comment treated
small, short-lived fixtures as an exception, but the workspace rule permits no run artifacts in the
shared RAM-backed `/tmp` mount.

## Resolution

The helper now creates temporary fixture trees under the repository's gitignored `scratch/raw/` and
still lets `TemporaryDirectory` remove each tree at context exit. The 19-case containment selftest
passes from the new location.
