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

// THE CONTRACT, from the measurement in bios_threads.h: SLUS_005.61 passes a2 = 0 on every
// OpenTh call and relies on the thread inheriting the creating context's global base. Taking
// that 0 at face value resumed every task with $gp = 0, and MMX4's code is $gp`-relative
// throughout, so each of those tasks read and wrote the low 16 KB of RAM in place of its own
// statics. These cases pin the policy in BOTH directions, because the previous behaviour -
// honouring the guest's zero - is the defect, and a test that only covers the fixed direction
// would pass on a policy that always returned the caller's gp.
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
  // A context that has already lost its gp opens a thread. The port must NOT fabricate a
  // global base here: the switch census is what reports that case, and a made-up value would
  // hide it behind a thread that appears to run.
  check(resolveThreadGlobalPointer(0u, 0u) == 0u, "two zeros stay zero; the port does not invent a global base");
}

void policy_is_not_simply_the_caller() {
  using x4::bios_threads::resolveThreadGlobalPointer;
  // The negative for "always return the caller's gp", which would pass the inheritance case
  // and fail only here.
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
