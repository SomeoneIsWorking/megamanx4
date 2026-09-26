#!/usr/bin/env bash
# Mutation harness: prove each hermetic test class can FAIL. A test that cannot fail is worse
# than no test, so every claim in tests/test_x4_visibility_cull.cpp is broken on purpose, once,
# and the resulting failure is recorded. Maintainer RE/CI aid; not a product path.
set -u
cd "$(dirname "$0")/.."

SRC=game/core/visibility_cull.cpp
HDR=game/core/visibility_cull.h
TST=tests/test_x4_visibility_cull.cpp
BAK=scratch/mutation_backup
mkdir -p "$BAK"
cp "$SRC" "$BAK/src" ; cp "$HDR" "$BAK/hdr" ; cp "$TST" "$BAK/tst"

restore() { cp "$BAK/src" "$SRC" ; cp "$BAK/hdr" "$HDR" ; cp "$BAK/tst" "$TST" ; }
trap restore EXIT

run() { # $1 = label, $2 = python mutation
  local label="$1" mutation="$2"
  restore
  python3 - "$SRC" "$HDR" <<PY
import sys, pathlib
src, hdr = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
$mutation
PY
  if ! cmp -s "$SRC" "$BAK/src" || ! cmp -s "$HDR" "$BAK/hdr" || ! cmp -s "$TST" "$BAK/tst"; then :; else
    echo "MUTATION-NOOP $label (nothing changed; the test would prove nothing)"; return
  fi
  if ! cmake --build build --target mmx4_visibility_cull_test -j"$(nproc)" >/dev/null 2>&1; then
    echo "BUILD-FAIL  $label"; return
  fi
  local out
  out=$(./build/mmx4_visibility_cull_test 2>&1)
  if printf '%s' "$out" | grep -q "x4_visibility_cull:"; then
    echo "SURVIVED   $label  <-- the test did NOT catch this"
  else
    echo "CAUGHT     $label  :: $(printf '%s' "$out" | grep -m1 -E 'FAIL|error:')"
  fi
}

run "M1 window forgets the plan margin (the exact defect)" \
  's = src.read_text()
s = s.replace("  const int shifted = half + margin;", "  const int shifted = half;  // MUTANT: margin dropped")
s = s.replace("return {shifted, 2 * shifted + RetailScreen::kWidth};", "return {shifted, 2 * half + RetailScreen::kWidth};")
src.write_text(s)'

run "M2 window widens only the right edge" \
  's = src.read_text()
s = s.replace("return {shifted, 2 * shifted + RetailScreen::kWidth};",
              "return {half, 2 * (half + margin) + RetailScreen::kWidth};  // MUTANT: left edge fixed")
src.write_text(s)'

run "M3 unsigned compare replaced by a signed one" \
  's = src.read_text()
s = s.replace("  return static_cast<std::uint16_t>(shifted) < static_cast<std::uint16_t>(bound_);",
              "  return static_cast<std::int32_t>(shifted) < static_cast<std::int32_t>(bound_);  // MUTANT")
src.write_text(s)'

run "M4 compare in 32 bits instead of masking to 16" \
  's = src.read_text()
s = s.replace("  return static_cast<std::uint16_t>(shifted) < static_cast<std::uint16_t>(bound_);",
              "  return shifted < static_cast<std::uint32_t>(bound_);  // MUTANT: no 16-bit mask")
src.write_text(s)'

run "M5 vertical window built on the horizontal width" \
  's = src.read_text()
s = s.replace("  return {half, 2 * half + RetailScreen::kHeight};",
              "  return {half, 2 * half + RetailScreen::kWidth};  // MUTANT: 320 instead of 240")
src.write_text(s)'

run "M6 QuadObj reuses BaseObj background offset +0x14" \
  'import re
h = hdr.read_text()
h2 = re.sub(r"kQuadObjectBackgroundOffset = 0x37u", "kQuadObjectBackgroundOffset = 0x14u", h)
assert h2 != h, "M6 pattern did not match"
hdr.write_text(h2)'

run "M7 background byte ignored (always layer 0)" \
  's = src.read_text()
s2 = s.replace("  return layer < 0 ? -1 : layer;", "  return layer < 0 ? 0 : layer;  // MUTANT")
assert s2 != s, "M7 pattern did not match"
src.write_text(s2)'

run "M8 quad corner loop stops after the first corner" \
  's = src.read_text()
s2 = s.replace("  for (std::uint32_t corner = 0; corner < 4; ++corner) {",
               "  for (std::uint32_t corner = 0; corner < 1; ++corner) {  // MUTANT")
assert s2 != s, "M8 pattern did not match"
src.write_text(s2)'

run "M9 measured site 0x8002B3C0 given the 32/32 slack" \
  'import re
h = hdr.read_text()
h2 = h.replace("0x8002B3C0u, RetailSlack::kWideX, RetailSlack::kWideY,",
               "0x8002B3C0u, RetailSlack::kWideX, RetailSlack::kWideX,")
assert h2 != h, "M9 pattern did not match"
hdr.write_text(h2)'

run "M10 position load sign-extends instead of zero-extending" \
  's = src.read_text()
s = s.replace("  const std::uint32_t position = core.mem_r16(object + offsets.xInteger);",
              "  const std::uint32_t position = static_cast<std::uint32_t>(static_cast<std::int32_t>(static_cast<std::int16_t>(core.mem_r16(object + offsets.xInteger))));  // MUTANT")
src.write_text(s)'

run "M11 on_screen published at the wrong offset" \
  's = s0 = src.read_text()
s = s.replace("inline constexpr std::uint32_t kOnScreenOffset", "inline constexpr std::uint32_t kOnScreenOffsetX")
h = hdr.read_text()
h = h.replace("inline constexpr std::uint32_t kOnScreenOffset = 0x03u;",
              "inline constexpr std::uint32_t kOnScreenOffset = 0x04u;  // MUTANT")
hdr.write_text(h)'

run "M12 plan margin is not clamped at zero" \
  'h = hdr.read_text()
h = h.replace("  int horizontalMargin() const {\n    return margin_ > 0 ? margin_ : 0;\n  }",
              "  int horizontalMargin() const {\n    return margin_;  // MUTANT: no clamp\n  }")
hdr.write_text(h)'

run "M13 layer-0 site marked as reading the object byte" \
  'import re
h = hdr.read_text()
h2 = re.sub(r"(kBaseOffScreenLayerZero\{.*?)true\s*\};", r"\1false};  // MUTANT", h, flags=re.S)
assert h2 != h, "M13 pattern did not match"
hdr.write_text(h2)'

restore
cmake --build build --target mmx4_visibility_cull_test -j"$(nproc)" >/dev/null 2>&1
echo "restored; baseline:"
./build/mmx4_visibility_cull_test 2>&1 | grep "x4_visibility_cull:"
