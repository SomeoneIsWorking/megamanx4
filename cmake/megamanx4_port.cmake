# cmake/megamanx4_port.cmake — what this repo builds, and what it deliberately refuses to build yet.
#
# Three targets:
#
#   psxport            the framework static library. Always configured, so
#                      `cmake --build build --target psxport` works from a bare clone of this repo with
#                      nothing game-specific present. (psxport_smoke, the framework's agnosticism proof,
#                      CANNOT be built from a consumer tree — docs/issues/0001. Leave
#                      -DPSXPORT_BUILD_SMOKE at its OFF default.)
#   megamanx4_seam     AN OBJECT LIBRARY over every first-party game/core TU. It COMPILES but does not
#                      link, which is exactly the check that is possible
#                      before a substrate exists: it proves X4Runtime and its bounded legacy facts
#                      satisfy the pinned framework seam — every designator and virtual binds — AND
#                      that the three pc_enh CVars compile against the
#                      framework's config_var.h / config_vars.h. That is the gate for this repo today.
#   megamanx4_port     the game binary. Configured ONLY when generated/rec_sources.cmake exists, i.e.
#                      once tools/ensure_recomp.py has emitted the substrate. A loud STATUS message
#                      identifies the missing generated input rather than producing a stub.

option(PSXPORT_BUILD_PORT "Build the Mega Man X4 native port binary (needs generated/)" ON)

# The framework static library. Always included so `psxport` is buildable even when the game target is
# off. Never re-spell `external/psxport` here — ${PSXPORT_DIR} is the one spelling (CMakeLists.txt).
include(${PSXPORT_DIR}/cmake/psxport.cmake)

# ---- the seam, compile-only --------------------------------------------------------------------
# This includes every first-party translation unit. recomp_register.cpp has an honest no-substrate
# body until generated code exists; compiling it here keeps it in the real compile database used by
# clang-tidy rather than leaving one source outside every gate.
set(SEAM_SRC
  game/core/bios_threads.cpp
  game/core/fast_wait.cpp
  game/core/game_config.cpp
  game/core/game_hooks.cpp
  game/core/enhancements.cpp
  game/core/main.cpp
  game/core/recomp_register.cpp
  game/core/title_quad.cpp
  game/core/vsync_sync.cpp
  game/core/widescreen_controller.cpp
  game/core/x4_context.cpp
  game/core/x4_runtime.cpp
)
add_library(megamanx4_seam OBJECT ${SEAM_SRC})
# C++20, NOT the 17 the sibling trees' seam targets use. DEVIATION WITH A REASON: enhancements.cpp
# declares psx::config::BoolVar objects, and the framework's config_var.h is written against C++20-era
# headers and is built at C++20 inside libpsxport. Dropping enhancements.cpp from the gate to keep the
# standard at 17 would have been the wrong trade — the enhancement knobs are precisely the thing worth
# compile-checking here.
set_target_properties(megamanx4_seam PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(megamanx4_seam PRIVATE game game/core)
# Links only for its INTERFACE include directories — an OBJECT library performs no link step, which is
# the whole point: no substrate is needed to check that the seam is well-formed.
target_link_libraries(megamanx4_seam PRIVATE psxport)
target_compile_options(megamanx4_seam PRIVATE -g)

include(CTest)
if(BUILD_TESTING)
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  add_test(
    NAME cpp_policy
    COMMAND ${Python3_EXECUTABLE} ${PSXPORT_DIR}/tools/check_cpp_style.py
            --root ${CMAKE_SOURCE_DIR}
            --compile-commands ${CMAKE_BINARY_DIR}
  )
  add_test(
    NAME launcher_policy
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/test_run.py
  )
  add_test(
    NAME vsync_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_vsync.py --check --selftest
  )
  add_test(
    NAME cd_irq_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_cd_irq.py --check --selftest
  )
  add_test(
    NAME projection_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_projection.py --check --selftest
  )
  add_test(
    NAME title_composition_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_title_composition.py --check --selftest
  )
  add_test(
    NAME title_quad_ownership_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/re_title_quad.py --check --selftest
  )
  add_test(
    NAME no_temporal_source_dependency
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_no_temporal_dependency.py
            --check --selftest
  )
  add_test(
    NAME thread_evidence
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_threads.py --check --selftest
  )
  add_executable(mmx4_runtime_test
    ${CMAKE_SOURCE_DIR}/game/core/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/core/fast_wait.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_runtime.cpp
    ${CMAKE_SOURCE_DIR}/game/core/enhancements.cpp
    ${CMAKE_SOURCE_DIR}/game/core/game_config.cpp
    ${CMAKE_SOURCE_DIR}/game/core/game_hooks.cpp
    ${CMAKE_SOURCE_DIR}/game/core/recomp_register.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/game/core/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/core/widescreen_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_runtime.cpp
  )
  target_include_directories(mmx4_runtime_test PRIVATE game game/core)
  target_link_libraries(mmx4_runtime_test PRIVATE psxport)
  set_target_properties(mmx4_runtime_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_runtime COMMAND mmx4_runtime_test)
  add_executable(mmx4_player_object_test
    ${CMAKE_SOURCE_DIR}/tests/test_x4_player_object.cpp
  )
  target_include_directories(mmx4_player_object_test PRIVATE game game/core)
  target_link_libraries(mmx4_player_object_test PRIVATE psxport)
  set_target_properties(mmx4_player_object_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_player_object COMMAND mmx4_player_object_test)
  add_executable(mmx4_title_quad_test
    ${CMAKE_SOURCE_DIR}/game/core/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_title_quad.cpp
  )
  target_include_directories(mmx4_title_quad_test PRIVATE game game/core)
  target_link_libraries(mmx4_title_quad_test PRIVATE psxport)
  set_target_properties(mmx4_title_quad_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_title_quad COMMAND mmx4_title_quad_test)
endif()

if(NOT PSXPORT_BUILD_PORT)
  return()
endif()

if(NOT EXISTS ${CMAKE_SOURCE_DIR}/generated/rec_sources.cmake)
  message(STATUS
    "megamanx4_port: NOT configured — generated/rec_sources.cmake is absent, i.e. the recompiled "
    "substrate is absent. Run `python3 tools/ensure_recomp.py` after provisioning SLUS_005.61; "
    "RE-02's retail-binary bootstrap is verified. NOTE that RE-01's boot group is verified and RE-03 "
    "(overlay load bases) is ➖ skip-by-design here — this game has NO code overlays, measured; the "
    "boot executable is the whole engine. `--target megamanx4_seam` is the gate that DOES run today.")
  return()
endif()

# ---- the recompiled substrate --------------------------------------------------------------------
# emit.py writes the exact TU list to generated/rec_sources.cmake (GEN_REC_SRCS, basenames), so the set
# is deterministic — no globbing, which would wrongly pull unlinked stub TUs.
#
# -foptimize-sibling-calls IS REQUIRED, NOT an optimisation nicety: a guest TAIL JUMP is emitted as
# `dispatch(c,x); return;` in tail position and the guest uses such tail jumps for loops that iterate
# indefinitely. Without sibling-call optimisation each iteration becomes a real C call, the stack grows
# per loop, and the process SIGSEGVs.
include(${CMAKE_SOURCE_DIR}/generated/rec_sources.cmake)
list(TRANSFORM GEN_REC_SRCS PREPEND generated/)
set_source_files_properties(${GEN_REC_SRCS}
  PROPERTIES LANGUAGE CXX
  COMPILE_OPTIONS "-O1;-foptimize-sibling-calls;-fno-strict-aliasing;-fwrapv")

add_executable(megamanx4_port ${SEAM_SRC} ${GEN_REC_SRCS})

# Select the measured generated-symbol adapter in recomp_register.cpp.
target_compile_definitions(megamanx4_port PRIVATE MMX4_HAVE_SUBSTRATE=1)

# The framework's SDL_GPU shader header is produced by a psxport custom target; gpu_vk.cpp (inside
# libpsxport) needs it present before this target's link ordering.
add_dependencies(megamanx4_port gen_gpu_shaders)

set_target_properties(megamanx4_port PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON
  ENABLE_EXPORTS ON                                    # -rdynamic: watchdog backtrace symbol names
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR}/scratch/bin)

# Only game/* include dirs here — the framework's (runtime, generated, vendored backends, SDL, freetype)
# are inherited PUBLICly from the psxport link below.
target_include_directories(megamanx4_port PRIVATE game game/core)

target_compile_options(megamanx4_port PRIVATE -w -O2 -g
  ${SDL3_CFLAGS_OTHER} ${FREETYPE_CFLAGS_OTHER})

target_link_libraries(megamanx4_port PRIVATE psxport)

if(BUILD_TESTING)
  # The linked-product closure can only be checked when the generated substrate exists and therefore
  # the shipping target exists. Keep this registration below add_executable(): a clean clone without
  # generated/ must still configure and run its seam/source gates instead of failing on a generator
  # expression that names a target the build deliberately did not create.
  add_test(
    NAME no_temporal_binary_dependency
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_no_temporal_dependency.py
            --binary $<TARGET_FILE:megamanx4_port>
  )
endif()
