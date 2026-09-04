#pragma once

#include <cstdint>

class Core;

namespace x4::bios_threads {
class Service;
}

namespace x4::movie {

inline constexpr std::uint32_t kGeneralMovie = 0x80018000u;
inline constexpr std::uint32_t kCapcomMovie = 0x800182E8u;
inline constexpr std::uint32_t kMovieFrame = 0x80018B88u;

// Called only from authenticated guest bodies at measured field waits. The shipping callback returns
// a typed FrameBoundary; the BIOS-thread host owner parks and resumes the existing task fiber.
void yieldField(Core *core, std::uint32_t returnAddress);
void yieldField(Core &core, std::uint32_t returnAddress, bios_threads::Service &threads);
void registerOverrides(Core &core);

} // namespace x4::movie
