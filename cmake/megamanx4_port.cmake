# Mega Man X4's product consumes the authenticated executable at runtime. psxport's Lightrec
# executor owns all non-native guest instructions; no build step emits guest source or objects.

# The framework static library. Always included so `psxport` is buildable even when the game target is
# off. Never re-spell `external/psxport` here — ${PSXPORT_DIR} is the one spelling (CMakeLists.txt).
include(${PSXPORT_DIR}/cmake/psxport.cmake)

# ---- title sources -----------------------------------------------------------------------------
set(SEAM_SRC
  game/core/bios_threads.cpp
  game/core/cd_control_boundary.cpp
  game/core/cd_controller.cpp
  game/core/command_line.cpp
  game/core/display_init.cpp
  game/core/fast_wait.cpp
  game/core/game_config.cpp
  game/core/game_hooks.cpp
  game/core/gpu_timeout.cpp
  game/core/guest_execution.cpp
  game/core/enhancements.cpp
  game/core/main.cpp
  game/core/movie_field.cpp
  game/core/movie_cleanup.cpp
  game/core/music_stream.cpp
  game/core/native_overrides.cpp
  game/core/startup_cd.cpp
  game/core/stream_interrupt.cpp
  game/core/stream_field.cpp
  game/core/stream_startup.cpp
  game/core/title_layout.cpp
  game/core/title_quad.cpp
  game/core/vsync_sync.cpp
  game/core/widescreen_controller.cpp
  game/core/x4_context.cpp
  game/core/x4_frame_driver.cpp
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
  add_library(x4_guest_execution STATIC
    ${CMAKE_SOURCE_DIR}/game/core/guest_execution.cpp
  )
  target_include_directories(x4_guest_execution PUBLIC game game/core)
  target_link_libraries(x4_guest_execution PUBLIC psxport)
  set_target_properties(x4_guest_execution PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
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
    ${CMAKE_SOURCE_DIR}/game/core/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/game/core/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/display_init.cpp
    ${CMAKE_SOURCE_DIR}/game/core/fast_wait.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_runtime.cpp
    ${CMAKE_SOURCE_DIR}/game/core/enhancements.cpp
    ${CMAKE_SOURCE_DIR}/game/core/game_config.cpp
    ${CMAKE_SOURCE_DIR}/game/core/game_hooks.cpp
    ${CMAKE_SOURCE_DIR}/game/core/gpu_timeout.cpp
    ${CMAKE_SOURCE_DIR}/game/core/movie_field.cpp
    ${CMAKE_SOURCE_DIR}/game/core/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/core/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/core/native_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/core/startup_cd.cpp
    ${CMAKE_SOURCE_DIR}/game/core/stream_interrupt.cpp
    ${CMAKE_SOURCE_DIR}/game/core/stream_field.cpp
    ${CMAKE_SOURCE_DIR}/game/core/stream_startup.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_layout.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/game/core/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/core/widescreen_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_frame_driver.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_runtime.cpp
  )
  target_include_directories(mmx4_runtime_test PRIVATE game game/core)
  target_link_libraries(mmx4_runtime_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_runtime_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_runtime COMMAND mmx4_runtime_test)
  add_executable(mmx4_cd_control_boundary_test
    ${CMAKE_SOURCE_DIR}/game/core/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_cd_control_boundary.cpp
  )
  target_include_directories(mmx4_cd_control_boundary_test PRIVATE game game/core)
  target_link_libraries(mmx4_cd_control_boundary_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_cd_control_boundary_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_cd_control_boundary COMMAND mmx4_cd_control_boundary_test)
  add_executable(mmx4_movie_cleanup_test
    ${CMAKE_SOURCE_DIR}/game/core/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/core/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/game/core/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_movie_cleanup.cpp
  )
  target_include_directories(mmx4_movie_cleanup_test PRIVATE game game/core)
  target_link_libraries(mmx4_movie_cleanup_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_movie_cleanup_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_movie_cleanup COMMAND mmx4_movie_cleanup_test)
  add_executable(mmx4_command_line_test
    ${CMAKE_SOURCE_DIR}/game/core/command_line.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_command_line.cpp
  )
  target_include_directories(mmx4_command_line_test PRIVATE game/core)
  set_target_properties(mmx4_command_line_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_command_line COMMAND mmx4_command_line_test)
  add_executable(mmx4_frame_driver_test
    ${CMAKE_SOURCE_DIR}/game/core/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/core/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/core/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_frame_driver.cpp
    ${CMAKE_SOURCE_DIR}/game/core/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_frame_driver.cpp
  )
  target_include_directories(mmx4_frame_driver_test PRIVATE game game/core)
  target_link_libraries(mmx4_frame_driver_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_frame_driver_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_frame_driver COMMAND mmx4_frame_driver_test)
  add_executable(mmx4_music_stream_test
    ${CMAKE_SOURCE_DIR}/game/core/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_music_stream.cpp
  )
  target_include_directories(mmx4_music_stream_test PRIVATE game game/core)
  target_link_libraries(mmx4_music_stream_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_music_stream_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_music_stream COMMAND mmx4_music_stream_test)
  add_executable(mmx4_startup_cd_test
    ${CMAKE_SOURCE_DIR}/game/core/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/startup_cd.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_startup_cd.cpp
  )
  target_include_directories(mmx4_startup_cd_test PRIVATE game game/core)
  target_link_libraries(mmx4_startup_cd_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_startup_cd_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_startup_cd COMMAND mmx4_startup_cd_test)
  add_executable(mmx4_gpu_timeout_test
    ${CMAKE_SOURCE_DIR}/game/core/gpu_timeout.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_gpu_timeout.cpp
  )
  target_include_directories(mmx4_gpu_timeout_test PRIVATE game game/core)
  target_link_libraries(mmx4_gpu_timeout_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_gpu_timeout_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_gpu_timeout COMMAND mmx4_gpu_timeout_test)
  add_executable(mmx4_display_init_test
    ${CMAKE_SOURCE_DIR}/game/core/display_init.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_display_init.cpp
  )
  target_include_directories(mmx4_display_init_test PRIVATE game game/core)
  target_link_libraries(mmx4_display_init_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_display_init_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_display_init COMMAND mmx4_display_init_test)
  add_executable(mmx4_stream_startup_test
    ${CMAKE_SOURCE_DIR}/game/core/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/core/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/core/stream_field.cpp
    ${CMAKE_SOURCE_DIR}/game/core/stream_startup.cpp
    ${CMAKE_SOURCE_DIR}/game/core/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_stream_startup.cpp
  )
  target_include_directories(mmx4_stream_startup_test PRIVATE game game/core)
  target_link_libraries(mmx4_stream_startup_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_stream_startup_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_stream_startup COMMAND mmx4_stream_startup_test)
  add_executable(mmx4_stream_interrupt_test
    ${CMAKE_SOURCE_DIR}/game/core/stream_interrupt.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_stream_interrupt.cpp
  )
  target_include_directories(mmx4_stream_interrupt_test PRIVATE game game/core)
  target_link_libraries(mmx4_stream_interrupt_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_stream_interrupt_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_stream_interrupt COMMAND mmx4_stream_interrupt_test)
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
    ${CMAKE_SOURCE_DIR}/game/core/enhancements.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_layout.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_title_quad.cpp
  )
  target_include_directories(mmx4_title_quad_test PRIVATE game game/core)
  target_link_libraries(mmx4_title_quad_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_title_quad_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_title_quad COMMAND mmx4_title_quad_test)
  add_executable(mmx4_title_layout_test
    ${CMAKE_SOURCE_DIR}/game/core/enhancements.cpp
    ${CMAKE_SOURCE_DIR}/game/core/title_layout.cpp
    ${CMAKE_SOURCE_DIR}/game/core/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_title_layout.cpp
  )
  target_include_directories(mmx4_title_layout_test PRIVATE game game/core)
  target_link_libraries(mmx4_title_layout_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_title_layout_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_title_layout COMMAND mmx4_title_layout_test)
endif()

add_executable(megamanx4_port ${SEAM_SRC})

# The framework's SDL_GPU shader header is produced by a psxport custom target; gpu_vk.cpp (inside
# libpsxport) needs it present before this target's link ordering.
add_dependencies(megamanx4_port gen_gpu_shaders)

set_target_properties(megamanx4_port PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON
  ENABLE_EXPORTS ON
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# Framework runtime headers and dependencies are inherited from psxport.
target_include_directories(megamanx4_port PRIVATE game game/core)

target_compile_options(megamanx4_port PRIVATE -O2 -g
  ${SDL3_CFLAGS_OTHER} ${FREETYPE_CFLAGS_OTHER})

target_link_libraries(megamanx4_port PRIVATE psxport)

if(BUILD_TESTING)
  add_test(
    NAME no_temporal_binary_dependency
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_no_temporal_dependency.py
            --binary $<TARGET_FILE:megamanx4_port>
  )
endif()
