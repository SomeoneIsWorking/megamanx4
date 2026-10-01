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
# SYMLINK to the workspace's live framework checkout when one exists, or clones psxport main on a
# machine that has none. So a fresh clone of this repo alone still builds standalone: that property is
# what "each game is its own project using psxport as the framework" means, and it must stay testable.
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

# The framework's OWN nested vendors (vendor/lucent, vendor/beetle-psx/deps/libchdr) belong to the
# checkout tools/psxport_fetch.py resolved: it initialises them non-recursively wherever it got the
# framework from. If they are somehow missing, the error comes from inside psxport with a clear "does
# not contain a CMakeLists.txt", and the fix is `git -C external/psxport submodule update --init
# <vendor>` in that checkout.
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
