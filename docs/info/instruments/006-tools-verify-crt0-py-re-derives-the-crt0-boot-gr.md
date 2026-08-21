---
id: I006
kind: instrument
status: trusted
created: 2026-08-12
---

## Instrument

`tools/verify_crt0.py` derives the crt0 boot group from a PS-X EXE, compares it with the shipping
`GameConfig`, and checks that psxport implements the required mechanisms.

## Validated by

2026-08-21: `--check` re-derived the retail group/range, matched 21/21 shipping facts, and located 15/15
framework mechanisms. `--selftest` passed 26/26 locally and 29/29 with Tomba!2's independent
cross-control. Its negatives mutate the executable, the shipping config, four framework mechanisms,
the entry point, and malformed corpora; each produces the opposite answer or a refusal.

Blind spots: immediate-only straight-line static analysis, no runtime observation. The shipping C++
and framework mechanisms are recognized from comment-stripped source text.

## Known failure modes

- Fixed 2026-08-12: the tool once compared the executable with its own duplicate expectation table,
  so wrong shipping constants passed. It now parses and compares the shipping file directly.
- Fixed 2026-08-21 (issue #6): the heap-store guards recognized only an obsolete one-line spelling.
  clang-format's braced form produced a false incompatibility and made two sabotage cases vacuous.
  Four GameConfig mutations had the same exact-whitespace defect. All recognizers and mutations now
  match semantic source shapes; deleting either real guard or changing the formatted config still
  produces the expected opposite answer.
