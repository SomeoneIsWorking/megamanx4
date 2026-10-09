include(${PSXPORT_DIR}/cmake/psxport.cmake)

# Include path shared by every first-party target.
set(X4_TITLE_DIRS
  ${CMAKE_SOURCE_DIR}/game/boot
  ${CMAKE_SOURCE_DIR}/game/execution
  ${CMAKE_SOURCE_DIR}/game/frame
  ${CMAKE_SOURCE_DIR}/game/input
  ${CMAKE_SOURCE_DIR}/game/media
  ${CMAKE_SOURCE_DIR}/game/render
  ${CMAKE_SOURCE_DIR}/game/title
  ${CMAKE_SOURCE_DIR}/game/ui
  ${CMAKE_SOURCE_DIR}/game/widescreen
)

set(SEAM_SRC
  game/boot/main.cpp
  game/boot/command_line.cpp
  game/boot/x4_runtime.cpp
  game/boot/x4_context.cpp
  game/frame/x4_frame_driver.cpp
  game/frame/vsync_sync.cpp
  game/input/input_path.cpp
  game/media/startup_cd.cpp
  game/media/cd_controller.cpp
  game/media/cd_control_boundary.cpp
  game/media/stream_startup.cpp
  game/media/stream_interrupt.cpp
  game/media/movie_cleanup.cpp
  game/media/music_cd.cpp
  game/media/music_stream.cpp
  game/media/fast_wait.cpp
  game/render/display_init.cpp
  game/render/gpu_timeout.cpp
  game/render/background_tiles.cpp
  game/render/background_overrides.cpp
  game/render/hud_anchor.cpp
  game/render/hud_overrides.cpp
  game/input/sequence_skip.cpp
  game/input/sequence_skip_overrides.cpp
  game/render/visibility_cull.cpp
  game/render/widened_objects.cpp
  game/render/cull_overrides.cpp
  game/render/vram_rect_queue.cpp
  game/widescreen/widescreen_controller.cpp
  game/ui/title_quad.cpp
  game/execution/guest_execution.cpp
  game/execution/native_overrides.cpp
  game/execution/bios_threads.cpp
  game/title/game_config.cpp
  game/title/game_hooks.cpp
  game/title/enhancements.cpp
)
add_library(megamanx4_seam OBJECT ${SEAM_SRC})
# C++20: enhancements.cpp uses psx::config::BoolVar, whose header needs it.
set_target_properties(megamanx4_seam PROPERTIES CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON)
target_include_directories(megamanx4_seam PRIVATE ${X4_TITLE_DIRS})
# Links only for include directories; an OBJECT library has no link step.
target_link_libraries(megamanx4_seam PRIVATE psxport)
target_compile_options(megamanx4_seam PRIVATE -g)

include(CTest)
if(BUILD_TESTING)
  add_library(x4_guest_execution STATIC
    ${CMAKE_SOURCE_DIR}/game/execution/guest_execution.cpp
  )
  target_include_directories(x4_guest_execution PUBLIC ${X4_TITLE_DIRS})
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
    NAME no_temporal_source_dependency
    COMMAND ${Python3_EXECUTABLE} -B ${CMAKE_SOURCE_DIR}/tools/verify_no_temporal_dependency.py
            --check --selftest
  )
  add_executable(mmx4_runtime_test
    ${CMAKE_SOURCE_DIR}/game/execution/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/render/display_init.cpp
    ${CMAKE_SOURCE_DIR}/game/media/fast_wait.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_runtime.cpp
    ${CMAKE_SOURCE_DIR}/game/title/enhancements.cpp
    ${CMAKE_SOURCE_DIR}/game/title/game_config.cpp
    ${CMAKE_SOURCE_DIR}/game/title/game_hooks.cpp
    ${CMAKE_SOURCE_DIR}/game/render/gpu_timeout.cpp
    ${CMAKE_SOURCE_DIR}/game/media/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/media/music_cd.cpp
    ${CMAKE_SOURCE_DIR}/game/media/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/execution/native_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/media/startup_cd.cpp
    ${CMAKE_SOURCE_DIR}/game/media/stream_interrupt.cpp
    ${CMAKE_SOURCE_DIR}/game/media/stream_startup.cpp
    ${CMAKE_SOURCE_DIR}/game/ui/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/game/render/background_tiles.cpp
    ${CMAKE_SOURCE_DIR}/game/render/background_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/render/hud_anchor.cpp
    ${CMAKE_SOURCE_DIR}/game/render/hud_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/input/sequence_skip.cpp
    ${CMAKE_SOURCE_DIR}/game/input/sequence_skip_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/render/cull_overrides.cpp
    ${CMAKE_SOURCE_DIR}/game/render/visibility_cull.cpp
    ${CMAKE_SOURCE_DIR}/game/render/widened_objects.cpp
    ${CMAKE_SOURCE_DIR}/game/render/vram_rect_queue.cpp
    ${CMAKE_SOURCE_DIR}/game/frame/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/input/input_path.cpp
    ${CMAKE_SOURCE_DIR}/game/widescreen/widescreen_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/game/frame/x4_frame_driver.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_runtime.cpp
  )
  target_include_directories(mmx4_runtime_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_runtime_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_runtime_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_runtime COMMAND mmx4_runtime_test)
  add_executable(mmx4_cd_control_boundary_test
    ${CMAKE_SOURCE_DIR}/game/media/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_cd_control_boundary.cpp
  )
  target_include_directories(mmx4_cd_control_boundary_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_cd_control_boundary_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_cd_control_boundary_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_cd_control_boundary COMMAND mmx4_cd_control_boundary_test)
  add_executable(mmx4_movie_cleanup_test
    ${CMAKE_SOURCE_DIR}/game/execution/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_control_boundary.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/media/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_movie_cleanup.cpp
  )
  target_include_directories(mmx4_movie_cleanup_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_movie_cleanup_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_movie_cleanup_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_movie_cleanup COMMAND mmx4_movie_cleanup_test)
  add_executable(mmx4_command_line_test
    ${CMAKE_SOURCE_DIR}/game/boot/command_line.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_command_line.cpp
  )
  target_include_directories(mmx4_command_line_test PRIVATE ${X4_TITLE_DIRS})
  set_target_properties(mmx4_command_line_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_command_line COMMAND mmx4_command_line_test)
  add_executable(mmx4_frame_driver_test
    ${CMAKE_SOURCE_DIR}/game/execution/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/media/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/media/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/game/frame/x4_frame_driver.cpp
    ${CMAKE_SOURCE_DIR}/game/frame/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/input/input_path.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_frame_driver.cpp
  )
  target_include_directories(mmx4_frame_driver_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_frame_driver_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_frame_driver_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_frame_driver COMMAND mmx4_frame_driver_test)
  add_executable(mmx4_music_stream_test
    ${CMAKE_SOURCE_DIR}/game/media/music_stream.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_music_stream.cpp
  )
  target_include_directories(mmx4_music_stream_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_music_stream_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_music_stream_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_music_stream COMMAND mmx4_music_stream_test)
  add_executable(mmx4_music_cd_test
    ${CMAKE_SOURCE_DIR}/game/media/music_cd.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_music_cd.cpp
  )
  target_include_directories(mmx4_music_cd_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_music_cd_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_music_cd_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_music_cd COMMAND mmx4_music_cd_test)
  add_executable(mmx4_startup_cd_test
    ${CMAKE_SOURCE_DIR}/game/media/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/media/startup_cd.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_startup_cd.cpp
  )
  target_include_directories(mmx4_startup_cd_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_startup_cd_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_startup_cd_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_startup_cd COMMAND mmx4_startup_cd_test)
  add_executable(mmx4_gpu_timeout_test
    ${CMAKE_SOURCE_DIR}/game/render/gpu_timeout.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_gpu_timeout.cpp
  )
  target_include_directories(mmx4_gpu_timeout_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_gpu_timeout_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_gpu_timeout_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_gpu_timeout COMMAND mmx4_gpu_timeout_test)
  add_executable(mmx4_vram_rect_queue_test
    ${CMAKE_SOURCE_DIR}/game/render/vram_rect_queue.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_vram_rect_queue.cpp
  )
  target_include_directories(mmx4_vram_rect_queue_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_vram_rect_queue_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_vram_rect_queue_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_vram_rect_queue COMMAND mmx4_vram_rect_queue_test)
  add_executable(mmx4_display_init_test
    ${CMAKE_SOURCE_DIR}/game/render/display_init.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_display_init.cpp
  )
  target_include_directories(mmx4_display_init_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_display_init_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_display_init_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_display_init COMMAND mmx4_display_init_test)
  add_executable(mmx4_stream_startup_test
    ${CMAKE_SOURCE_DIR}/game/execution/bios_threads.cpp
    ${CMAKE_SOURCE_DIR}/game/media/movie_cleanup.cpp
    ${CMAKE_SOURCE_DIR}/game/media/cd_controller.cpp
    ${CMAKE_SOURCE_DIR}/game/media/stream_startup.cpp
    ${CMAKE_SOURCE_DIR}/game/frame/vsync_sync.cpp
    ${CMAKE_SOURCE_DIR}/game/input/input_path.cpp
    ${CMAKE_SOURCE_DIR}/game/boot/x4_context.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_stream_startup.cpp
  )
  target_include_directories(mmx4_stream_startup_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_stream_startup_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_stream_startup_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_stream_startup COMMAND mmx4_stream_startup_test)
  add_executable(mmx4_stream_interrupt_test
    ${CMAKE_SOURCE_DIR}/game/media/stream_interrupt.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_stream_interrupt.cpp
  )
  target_include_directories(mmx4_stream_interrupt_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_stream_interrupt_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_stream_interrupt_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_stream_interrupt COMMAND mmx4_stream_interrupt_test)
  add_executable(mmx4_player_object_test
    ${CMAKE_SOURCE_DIR}/tests/test_x4_player_object.cpp
  )
  target_include_directories(mmx4_player_object_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_player_object_test PRIVATE psxport)
  set_target_properties(mmx4_player_object_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_player_object COMMAND mmx4_player_object_test)
  add_executable(mmx4_title_quad_test
    ${CMAKE_SOURCE_DIR}/game/ui/title_quad.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_title_quad.cpp
  )
  target_include_directories(mmx4_title_quad_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_title_quad_test PRIVATE x4_guest_execution)
  set_target_properties(mmx4_title_quad_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_title_quad COMMAND mmx4_title_quad_test)
  # Predicate only; cull_overrides.cpp (guest dispatcher) stays out so the test is hermetic.
  add_executable(mmx4_visibility_cull_test
    ${CMAKE_SOURCE_DIR}/game/render/visibility_cull.cpp
    ${CMAKE_SOURCE_DIR}/game/render/widened_objects.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_visibility_cull.cpp
  )
  target_include_directories(mmx4_visibility_cull_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_visibility_cull_test PRIVATE psxport)
  set_target_properties(mmx4_visibility_cull_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_visibility_cull COMMAND mmx4_visibility_cull_test)
  # Layout only; background_overrides.cpp (guest dispatcher) stays out so the test is hermetic.
  add_executable(mmx4_background_tiles_test
    ${CMAKE_SOURCE_DIR}/game/render/background_tiles.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_background_tiles.cpp
  )
  target_include_directories(mmx4_background_tiles_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_background_tiles_test PRIVATE psxport)
  set_target_properties(mmx4_background_tiles_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_background_tiles COMMAND mmx4_background_tiles_test)
  # Packet shifting only; hud_overrides.cpp (guest dispatcher) stays out so the test is hermetic.
  add_executable(mmx4_hud_anchor_test
    ${CMAKE_SOURCE_DIR}/game/render/hud_anchor.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_hud_anchor.cpp
  )
  target_include_directories(mmx4_hud_anchor_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_hud_anchor_test PRIVATE psxport)
  set_target_properties(mmx4_hud_anchor_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_hud_anchor COMMAND mmx4_hud_anchor_test)
  # The skip rule only; sequence_skip_overrides.cpp (guest dispatcher) stays out so the test is hermetic.
  add_executable(mmx4_sequence_skip_test
    ${CMAKE_SOURCE_DIR}/game/input/sequence_skip.cpp
    ${CMAKE_SOURCE_DIR}/tests/test_x4_sequence_skip.cpp
  )
  target_include_directories(mmx4_sequence_skip_test PRIVATE ${X4_TITLE_DIRS})
  target_link_libraries(mmx4_sequence_skip_test PRIVATE psxport)
  set_target_properties(mmx4_sequence_skip_test PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
  )
  add_test(NAME x4_sequence_skip COMMAND mmx4_sequence_skip_test)
  # Needs the player's disc; exit code 77 skips when none is present.
  # uv run because the script imports from the locked project environment.
  find_program(X4_UV_EXECUTABLE uv)
  if(X4_UV_EXECUTABLE)
    add_test(
      NAME task_resume_evidence
      # --product must be this build's binary, not the script's default build/bin path.
      COMMAND ${X4_UV_EXECUTABLE} run --frozen python ${CMAKE_SOURCE_DIR}/tools/verify_task_resume.py
              --product ${CMAKE_BINARY_DIR}/bin/megamanx4_port
    )
    set_tests_properties(task_resume_evidence PROPERTIES SKIP_RETURN_CODE 77 TIMEOUT 900)
  endif()
endif()

add_executable(megamanx4_port ${SEAM_SRC})

# gpu_vk.cpp in libpsxport needs the generated SDL_GPU shader header first.
add_dependencies(megamanx4_port gen_gpu_shaders)

set_target_properties(megamanx4_port PROPERTIES
  CXX_STANDARD 20 CXX_STANDARD_REQUIRED ON
  ENABLE_EXPORTS ON
  RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

target_include_directories(megamanx4_port PRIVATE ${X4_TITLE_DIRS})

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

add_executable(mmx4_thread_global_pointer_test
  ${CMAKE_SOURCE_DIR}/tests/test_x4_thread_global_pointer.cpp)
# r3000.h (via bios_threads.h) comes through psxport's exported include directories.
target_include_directories(mmx4_thread_global_pointer_test PRIVATE ${X4_TITLE_DIRS})
target_link_libraries(mmx4_thread_global_pointer_test PRIVATE psxport)
set_target_properties(mmx4_thread_global_pointer_test PROPERTIES
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
)
add_test(NAME x4_thread_global_pointer COMMAND mmx4_thread_global_pointer_test)
