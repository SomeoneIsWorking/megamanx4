#pragma once

#include <cstdint>

class Core;

namespace x4::bios_threads {
class Service;
}

// Build-derived, executable-authenticated movie bodies. The original generated supers remain
// compiled; tools/generate_x4_movie_fiber.py changes only three measured libetc VSync call sites to
// this title-owned field boundary.
void x4_native_general_movie(Core *core);
void x4_native_capcom_movie(Core *core);
void x4_native_movie_frame(Core *core);

namespace x4::movie {

inline constexpr std::uint32_t kGeneralMovie = 0x80018000u;
inline constexpr std::uint32_t kCapcomMovie = 0x800182E8u;
inline constexpr std::uint32_t kMovieFrame = 0x80018B88u;

// Called only from the build-derived bodies at executable-authenticated field waits. This parks the
// existing BIOS-thread fiber; it never dispatches or emulates guest VSync.
void yieldField(Core *core, std::uint32_t returnAddress);
void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads);
void registerOverrides();

} // namespace x4::movie
