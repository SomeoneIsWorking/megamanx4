#!/usr/bin/env python3
"""Provision, build, and launch the Mega Man X4 port."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
PLAYER_BUILD_DIR = "scratch/build/player"
CYAN = "\033[1;36m"
RED = "\033[1;31m"
RESET = "\033[0m"


class LauncherFailure(RuntimeError):
    """A user-facing launcher refusal."""


class Host:
    """Narrow injectable seam around host discovery and process execution."""

    @staticmethod
    def which(name: str) -> str | None:
        return shutil.which(name)

    @staticmethod
    def run(args: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess:
        check = bool(kwargs.pop("check", False))
        return subprocess.run(list(args), check=check, **kwargs)

    @staticmethod
    def system() -> str:
        return platform.system()

    @staticmethod
    def linux_distribution() -> str:
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key == "ID":
                    return value.strip().strip('"').lower()
        except OSError:
            pass
        return "unknown"


def say(message: str, stdout: TextIO) -> None:
    print(f"{CYAN}[run]{RESET} {message}", file=stdout)


def package_command(host: Host, package: str) -> str | None:
    system = host.system()
    if system == "Darwin":
        commands = {
            "cmake": "brew install cmake",
            "git": "xcode-select --install",
            "pkg-config": "brew install pkg-config",
            "sdl3": "brew install sdl3",
        }
        return commands[package]
    if system == "Windows":
        commands = {
            "cmake": "winget install Kitware.CMake",
            "git": "winget install Git.Git",
            "pkg-config": "vcpkg install pkgconf",
            "sdl3": "vcpkg install sdl3",
        }
        return commands[package]
    if system != "Linux":
        return None

    distribution = host.linux_distribution()
    if distribution in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        commands = {
            "cmake": "sudo dnf install cmake",
            "git": "sudo dnf install git",
            "pkg-config": "sudo dnf install pkgconf-pkg-config",
            "sdl3": "sudo dnf install SDL3-devel",
        }
        return commands[package]
    if distribution in {"debian", "ubuntu", "linuxmint", "pop"}:
        commands = {
            "cmake": "sudo apt install cmake",
            "git": "sudo apt install git",
            "pkg-config": "sudo apt install pkg-config",
            "sdl3": "sudo apt install libsdl3-dev",
        }
        return commands[package]
    return None


def missing_dependency(host: Host, name: str, package: str) -> LauncherFailure:
    command = package_command(host, package)
    if command:
        return LauncherFailure(f"{name} not found. Install it with: {command}")
    system = host.system()
    distribution = host.linux_distribution() if system == "Linux" else "unknown"
    return LauncherFailure(
        f"{name} not found, and no package command is recorded for {system}/{distribution}; "
        "install it with your platform package manager and rerun"
    )


def require_tool(host: Host, name: str, package: str | None = None) -> str:
    resolved = host.which(name)
    if resolved is None:
        raise missing_dependency(host, name, package or name)
    return resolved


def run_stage(
    host: Host,
    args: Sequence[str],
    failure: str,
    *,
    root: Path,
    env: Mapping[str, str],
) -> None:
    try:
        result = host.run(args, cwd=root, env=dict(env), check=False)
    except OSError as exc:
        raise LauncherFailure(f"{failure}: {exc}") from exc
    if result.returncode != 0:
        raise LauncherFailure(failure)


def command_output(host: Host, args: Sequence[str], *, root: Path) -> tuple[int, str]:
    try:
        result = host.run(
            args,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError:
        return 127, ""
    return result.returncode, result.stdout.strip()


def compiler_arguments(host: Host, environment: Mapping[str, str]) -> list[str]:
    """Pass user choices through; otherwise prefer Clang and let CMake own discovery."""

    arguments = []
    if cc := environment.get("CC"):
        arguments.append(f"-DCMAKE_C_COMPILER={cc}")
    if cxx := environment.get("CXX"):
        arguments.append(f"-DCMAKE_CXX_COMPILER={cxx}")
    if arguments:
        return arguments
    if host.which("clang") is not None and host.which("clang++") is not None:
        return ["-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++"]
    return []


def cpu_jobs(host: Host, *, root: Path) -> str:
    for args in (["getconf", "_NPROCESSORS_ONLN"], ["sysctl", "-n", "hw.ncpu"]):
        returncode, output = command_output(host, args, root=root)
        if returncode == 0 and output.isdigit() and int(output) > 0:
            return output
    return "4"


def framework_revision(host: Host, path: Path, *, root: Path) -> tuple[str, bool]:
    returncode, revision = command_output(
        host, ["git", "-C", str(path), "rev-parse", "--short", "HEAD"], root=root
    )
    if returncode != 0 or not revision:
        revision = "?"
    _, status = command_output(
        host, ["git", "-C", str(path), "status", "--porcelain"], root=root
    )
    return revision, bool(status)


def announce_framework(
    host: Host, setting: str, path: Path, *, root: Path, stdout: TextIO
) -> None:
    revision, dirty = framework_revision(host, path, root=root)
    suffix = " +dirty" if dirty else ""
    if setting == "external/psxport":
        say(
            f"framework: external/psxport -> {path.resolve()} @ {revision}{suffix}",
            stdout,
        )
        return
    say(
        f"framework: *** {setting} *** (DEV CLONE {revision}{suffix}) — NOT the recorded pin",
        stdout,
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "disc", nargs="?", help="path to the user's Mega Man X4 disc image"
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="provision and build the default target without launching it",
    )
    return parser.parse_args(list(argv))


def run_launcher(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    host: Host | None = None,
    root: Path = ROOT,
    python_executable: str = sys.executable,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run the shipping launcher; injectable seams keep tests on this implementation."""

    environment = dict(os.environ if environ is None else environ)
    machine = host or Host()
    try:
        options = parse_args(argv)
        require_tool(machine, "cmake")
        require_tool(machine, "git")
        require_tool(machine, "pkg-config")
        run_stage(
            machine,
            ["pkg-config", "--exists", "sdl3"],
            str(missing_dependency(machine, "SDL3 development files", "sdl3")),
            root=root,
            env=environment,
        )

        compiler_options = compiler_arguments(machine, environment)
        jobs = cpu_jobs(machine, root=root)

        psxport_setting = environment.get("PSXPORT_DIR") or "external/psxport"
        if not environment.get("PSXPORT_DIR"):
            run_stage(
                machine,
                [python_executable, "tools/psxport_sync.py", "--auto"],
                "could not resolve external/psxport",
                root=root,
                env=environment,
            )
        psxport_path = Path(psxport_setting)
        if not psxport_path.is_absolute():
            psxport_path = root / psxport_path
        if not (psxport_path / "cmake" / "psxport.cmake").is_file():
            raise LauncherFailure(
                f"PSXPORT_DIR={psxport_setting} is not a psxport checkout"
            )
        announce_framework(
            machine, psxport_setting, psxport_path, root=root, stdout=stdout
        )

        provision_env = dict(environment)
        provision_env["PSXPORT_DIR"] = str(psxport_path)
        provision = [python_executable, "tools/extract_exe.py"]
        if options.disc:
            provision.append(options.disc)
        run_stage(
            machine,
            provision,
            "executable provisioning failed",
            root=root,
            env=provision_env,
        )
        run_stage(
            machine,
            [python_executable, "-B", "tools/ensure_recomp.py"],
            "recompiled substrate generation failed",
            root=root,
            env=provision_env,
        )

        say("building the native port…", stdout)
        configure = [
            "cmake",
            "-S",
            ".",
            "-B",
            PLAYER_BUILD_DIR,
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
            f"-DPSXPORT_DIR={psxport_path.absolute()}",
            f"-DPython3_EXECUTABLE={python_executable}",
            *compiler_options,
        ]
        run_stage(
            machine,
            configure,
            "cmake configure failed",
            root=root,
            env=environment,
        )
        run_stage(
            machine,
            ["cmake", "--build", PLAYER_BUILD_DIR, "-j", jobs, "--target", "megamanx4_port"],
            "native port build failed",
            root=root,
            env=environment,
        )
    except LauncherFailure as exc:
        print(f"{RED}[run] error:{RESET} {exc}", file=stderr)
        return 1

    if options.prepare_only:
        say("Mega Man X4 is built and ready.", stdout)
        return 0

    launch_env = dict(environment)
    if launch_env.get("PSXPORT_NOWINDOW"):
        launch_env["PSXPORT_VK_HEADLESS"] = "1"
    else:
        launch_env["PSXPORT_VK_WINDOW"] = "1"
    launch_env.setdefault("PSXPORT_ASSET_DIR", str(psxport_path))
    say("launching Mega Man X4…", stdout)
    try:
        result = machine.run(
            [str(root / "scratch" / "bin" / "megamanx4_port")],
            cwd=root,
            env=launch_env,
            check=False,
        )
    except OSError as exc:
        print(f"{RED}[run] error:{RESET} launch failed: {exc}", file=stderr)
        return 1
    return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    return run_launcher(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
