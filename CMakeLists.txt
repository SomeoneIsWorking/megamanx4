# Mega Man X4 (SLUS-00561, USA) — a PC-native port built on the psxport framework
# (external/psxport shared checkout or pin-resolved private clone).
#
# The framework supplies the PSX hardware layer and runtime Lightrec executor; this repository owns
# the title-native modules and authenticated SLUS_005.61 runtime-image policy.
#
# THIS PORT IS AN ENHANCEMENT PORT (CLAUDE.md): the game already runs at 60fps, so there is no native
# producer, no frame interpolation and no native renderer here. What this repo builds beyond the seam is
# three CVar-gated pc_enh gates (game/core/enhancements.{h,cpp}), which is why the seam target compiles
# that TU too — the enhancement knobs are compile-checked from the first commit.
cmake_minimum_required(VERSION 3.21)

# ccache, when available. This is maintainer acceleration only and never a product prerequisite.
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM)
  set(CMAKE_C_COMPILER_LAUNCHER   "${CCACHE_PROGRAM}")
  set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
  message(STATUS "ccache: ${CCACHE_PROGRAM}")
endif()

project(megamanx4 CXX C)

# PSXPORT_DIR — WHERE THE FRAMEWORK SOURCE COMES FROM. Defaults to external/psxport, which is no
# longer a git submodule (2026-08-16): tools/psxport_fetch.py --auto (called by run.sh) makes it a
# SYMLINK to the workspace's shared framework clone when one exists, or a private clone at this
# repo's psxport.pin on a fresh machine. So a fresh clone of this repo alone still builds standalone:
# that property is what "each game is its own project using psxport as the framework" means, and it
# must stay testable.
#
# Point it at a specific framework checkout to build against in-progress framework work:
#
#   cmake -S . -B build -DPSXPORT_DIR=/path/to/psxport
#
# It is a CACHE path, so it survives reconfigures. Everything else in this file and in cmake/ derives
# from it — never re-spell `external/psxport` at a call site, or the two halves of a build can come
# from different checkouts.
set(PSXPORT_DIR "${CMAKE_SOURCE_DIR}/external/psxport" CACHE PATH
    "psxport framework source directory (default: external/psxport)")
if(NOT EXISTS "${PSXPORT_DIR}/cmake/psxport.cmake")
  message(FATAL_ERROR "PSXPORT_DIR=${PSXPORT_DIR} has no cmake/psxport.cmake — "
                      "run `python3 tools/psxport_fetch.py --auto`, or point PSXPORT_DIR at a psxport checkout.")
endif()
message(STATUS "psxport framework: ${PSXPORT_DIR}")

# RECORD WHAT THIS CONFIGURE RESOLVED, so `external/psxport/tools/psxport_sync.py --check` can compare the framework
# you actually BUILT against with the one psxport.pin RECORDS. The framework is no longer a git
# submodule (external/psxport is a symlink to the workspace's shared clone, or a private clone at the
# pin — see tools/psxport_fetch.py); the pin is provenance, and this file is what keeps it honest.
execute_process(COMMAND git -C "${PSXPORT_DIR}" rev-parse HEAD
                OUTPUT_VARIABLE PSXPORT_RESOLVED_SHA OUTPUT_STRIP_TRAILING_WHITESPACE
                ERROR_QUIET RESULT_VARIABLE _psxport_rev_rc)
if(NOT _psxport_rev_rc EQUAL 0)
  set(PSXPORT_RESOLVED_SHA "unknown")   # honest: never silently record a plausible-looking sha
endif()
file(WRITE "${CMAKE_BINARY_DIR}/psxport_resolved.txt"
     "dir = ${PSXPORT_DIR}\ncommit = ${PSXPORT_RESOLVED_SHA}\n")
message(STATUS "psxport commit: ${PSXPORT_RESOLVED_SHA}")

# The framework's OWN nested vendors (vendor/lucent, vendor/beetle-psx/deps/libchdr) are the SHARED
# clone's concern now: they were initialized once in the dev clone, and external/psxport is a symlink
# to it. A fresh machine's private clone at the pin gets them from tools/psxport_fetch.py (which
# inits them non-recursively). If they are somehow missing, the error comes from inside psxport with a
# clear "does not contain a CMakeLists.txt", and the fix is `git -C external/psxport submodule update
# --init <vendor>` in the dev clone.
if(NOT EXISTS "${PSXPORT_DIR}/vendor/lucent/CMakeLists.txt")
  message(FATAL_ERROR "psxport's vendor/lucent is not checked out in the shared clone — run "
                      "`git -C ${PSXPORT_DIR} submodule update --init vendor/lucent` there once.")
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(ZLIB REQUIRED)
find_package(zstd CONFIG QUIET)
if(NOT TARGET zstd::libzstd_shared)
  find_library(ZSTD_LIBRARY zstd REQUIRED)
  add_library(zstd::libzstd_shared SHARED IMPORTED)
  set_target_properties(zstd::libzstd_shared PROPERTIES IMPORTED_LOCATION "${ZSTD_LIBRARY}")
endif()
find_package(Threads REQUIRED)

# libchdr (CHD access) comes from the Beetle PSX submodule NESTED under psxport (PSXPORT_DIR, above).
add_subdirectory(${PSXPORT_DIR}/vendor/beetle-psx/deps/libchdr
                 ${CMAKE_BINARY_DIR}/libchdr_build EXCLUDE_FROM_ALL)

include(cmake/megamanx4_port.cmake)

# THE LIVE PIN CHECK. Not a selftest: this runs the real function against this repository's real
# psxport.pin and the real build receipt, so it can fail when the pin is actually wrong.
#
# MEASURED 2026-09-27: every port in the workspace registered only a SELFTEST of the check function, run
# against a temporary fixture. A selftest asserts the function behaves; it cannot fail when this repo's
# pin is stale, which is why ten ports reported green while four pins were demonstrably stale. --build
# points at THIS build directory, configured moments ago, so the receipt is current by construction and
# the staleness guard cannot fire spuriously. Verified: perturbing psxport.pin turns it red.
if(BUILD_TESTING)
  add_test(
    NAME megamanx4_psxport_pin_live
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/external/psxport/tools/psxport_sync.py"
            --repo "${CMAKE_SOURCE_DIR}" --check --build "${CMAKE_BINARY_DIR}")
endif()

# The pin tool's own behaviour (staleness guard, a bump that records the commit the build RESOLVED) is
# tested once, in the framework (tests/test_psxport_sync.py). The only pin tool this repository ships
# is tools/psxport_fetch.py.

# The `jal` census's own selftest, registered WITHOUT media. It pins the two decode rules the
# boundary repair depends on - an absolute J-type target, and `$ra = PC + 8` for the delay slot - plus
# the negative that an entry nobody calls must come back empty rather than guessed. The first draft
# of this decoder took the J-type region nibble from the instruction word instead of the address, and
# the first draft of the selftest listed 0x0C000000 as a non-`jal` when it is opcode 3; both were
# caught here rather than in a hand-decoded listing.
#
# The OTHER mode, `--verify-boundaries`, re-derives the two hard-coded boundary constants in
# `vram_rect_queue.h` from the authenticated image and is deliberately NOT registered here: it needs
# the provisioned executable, and a registered test that cannot run in CI is the green-zero this
# workspace keeps meeting. Run it directly after provisioning:
#   uv run --frozen python tools/census_guest_call_sites.py --verify-boundaries
add_test(
  NAME megamanx4_guest_call_site_census_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/census_guest_call_sites.py"
          --selftest)

# probe_cursor_poll.py's refusals are the part worth gating: a tool that reports a
# confident answer when it has no measurement is the failure this project treats as worst.
# --selftest checks the refusal paths WITHOUT a port, so it is a real negative case in the
# gate rather than a construction test that passes whether or not the tool works.
add_test(
  NAME megamanx4_cursor_poll_selftest
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_cursor_poll.py"
          --selftest)

# probe_dispatch_table.py DECIDES REFUTATIONS, and a refutation from it withdraws a hypothesis, so
# it is the last tool in this repository that may be ungated. Its first version read 250 addresses
# that were not slots and produced a WRONG refutation at ~12 s, while the fault it claimed to explain
# happens at ~40 s (withdrawn in 4f915e5); it also shipped a NameError on any run with a non-zero
# slot. Both were caught by a human reading output. --selftest drives the sweep's refusal, the
# sighting-outranks-the-last-sweep decision, the missing-snapshot refusal, the classifier and the
# table walk, so a mutation to any of them turns the gate red. Guarded, unlike the two probe
# selftests above, because include(CTest) at the top of this file DOES define BUILD_TESTING, so here
# the guard is live rather than inert.
if(BUILD_TESTING)
  add_test(
    NAME megamanx4_dispatch_table_probe_selftest
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/probe_dispatch_table.py"
            --selftest)
endif()
