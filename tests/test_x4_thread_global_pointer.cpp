#include "bios_threads.h"

#include <cstdint>
#include <cstdio>

namespace {

int g_failures = 0;

void check(bool condition, const char *what) {
  if (!condition) {
    std::printf("FAIL: %s\n", what);
    ++g_failures;
  }
}

// SLUS_005.61 passes a2 = 0 to every OpenTh and relies on the thread inheriting the creator's $gp
// (MMX4 code is $gp-relative). Both directions are pinned: inherit, and never fabricate.
void policy_honours_an_explicit_request() {
  using x4::bios_threads::resolveThreadGlobalPointer;
  check(resolveThreadGlobalPointer(0x80001234u, 0x8012F418u) == 0x80001234u,
        "an explicit gp from the guest wins over the caller's");
}

void policy_inherits_when_the_guest_passes_zero() {
  using x4::bios_threads::resolveThreadGlobalPointer;
  check(resolveThreadGlobalPointer(0u, 0x8012F418u) == 0x8012F418u,
        "a zero request inherits the creating context's gp");
}

void policy_does_not_invent_a_global_base() {
  using x4::bios_threads::resolveThreadGlobalPointer;
  // A context that has already lost its gp must not get a fabricated base; the switch census reports it.
  check(resolveThreadGlobalPointer(0u, 0u) == 0u, "two zeros stay zero; the port does not invent a global base");
}

void policy_is_not_simply_the_caller() {
  using x4::bios_threads::resolveThreadGlobalPointer;
  // Negative for an always-return-the-caller's-gp policy.
  check(resolveThreadGlobalPointer(0xDEADBEEFu, 0x8012F418u) != 0x8012F418u,
        "the policy is not 'always the caller's gp'");
}

} // namespace

int main() {
  policy_honours_an_explicit_request();
  policy_inherits_when_the_guest_passes_zero();
  policy_does_not_invent_a_global_base();
  policy_is_not_simply_the_caller();

  if (g_failures != 0) {
    std::printf("%d check(s) failed\n", g_failures);
    return 1;
  }
  std::printf("thread gp policy: 4 checks passed\n");
  return 0;
}
