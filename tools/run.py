#!/usr/bin/env python3
"""Provision, build, verify, and launch the current Mega Man X4 port target."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
CYAN = "\033[1;36m"
RED = "\033[1;31m"
RESET = "\033[0m"


class LauncherFailure(RuntimeError):
    """A user-facing launcher refusal."""


class Host:
    """Narrow injectable seam around the real host process interface."""

    @staticmethod
    def which(name: str) -> str | None:
        return shutil.which(name)

    @staticmethod
    def run(args: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess:
        check = bool(kwargs.pop("check", False))
        return subprocess.run(list(args), check=check, **kwargs)


def say(message: str, stdout: TextIO) -> None:
    print(f"{CYAN}[run]{RESET} {message}", file=stdout)


def require_tool(host: Host, name: str) -> None:
    if host.which(name) is None:
        raise LauncherFailure(f"{name} not found")


def run_stage(
    host: Host,
    args: Sequence[str],
    failure: str,
    *,
    root: Path,
    env: Mapping[str, str],
    quiet: bool = False,
) -> None:
    try:
        result = host.run(
            args,
            cwd=root,
            env=dict(env),
            stdout=subprocess.DEVNULL if quiet else None,
            check=False,
        )
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
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return 127, ""
    return result.returncode, result.stdout.strip()


def require_clang(host: Host, variable: str, compiler: str, *, root: Path) -> None:
    _, version = command_output(host, [compiler, "--version"], root=root)
    if "clang" not in version.lower():
        raise LauncherFailure(f"{variable}={compiler} is not Clang")


def cpu_jobs(host: Host, *, root: Path) -> str:
    for args in (["getconf", "_NPROCESSORS_ONLN"], ["sysctl", "-n", "hw.ncpu"]):
        returncode, output = command_output(host, args, root=root)
        if returncode == 0 and output:
            return output
    return "4"


def framework_revision(host: Host, path: Path, *, root: Path) -> tuple[str, bool]:
    returncode, revision = command_output(
        host,
        ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
        root=root,
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


def sync_submodules(
    host: Host,
    *,
    root: Path,
    env: Mapping[str, str],
    stdout: TextIO,
) -> None:
    sync_tool = root / "external" / "psxport" / "scripts" / "sync-submodules.sh"
    if (
        host.which("git") is None
        or not (root / ".gitmodules").is_file()
        or not sync_tool.is_file()
    ):
        return
    if not (root / "external" / "mmx4" / "config").is_dir():
        say(
            "note: external/mmx4 (the AGPL reference decomp) is not checked out — the identity "
            "check will say it could not run. `git submodule update --init external/mmx4`",
            stdout,
        )
    run_stage(
        host, ["bash", str(sync_tool)], "submodule sync failed", root=root, env=env
    )


def run_launcher(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    host: Host | None = None,
    root: Path = ROOT,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run the shipping launcher; injectable arguments keep tests on this exact implementation."""

    environment = dict(os.environ if environ is None else environ)
    machine = host or Host()
    try:
        for tool in ("cmake", "python3", "pkg-config"):
            require_tool(machine, tool)
        run_stage(
            machine,
            ["pkg-config", "--exists", "sdl3"],
            "SDL3 not found (Linux: SDL3-devel/libsdl3-dev; macOS: brew install sdl3)",
            root=root,
            env=environment,
        )

        cc = environment.get("CC") or "clang"
        cxx = environment.get("CXX") or "clang++"
        require_clang(machine, "CC", cc, root=root)
        require_clang(machine, "CXX", cxx, root=root)
        jobs = cpu_jobs(machine, root=root)

        run_stage(
            machine,
            [sys.executable, "tools/psxport_sync.py", "--auto"],
            "could not resolve external/psxport",
            root=root,
            env=environment,
        )
        psxport_setting = environment.get("PSXPORT_DIR") or "external/psxport"
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
        sync_submodules(
            machine,
            root=root,
            env=environment,
            stdout=stdout,
        )

        provision_env = dict(environment)
        provision_env["PSXPORT_DIR"] = psxport_setting
        provision = [sys.executable, "tools/extract_exe.py"]
        if argv and argv[0]:
            provision.append(argv[0])
        run_stage(
            machine,
            provision,
            "executable provisioning failed",
            root=root,
            env=provision_env,
        )

        run_stage(
            machine,
            [sys.executable, "-B", "tools/ensure_recomp.py"],
            "recompiled substrate generation failed",
            root=root,
            env=provision_env,
        )

        say("building the native port…", stdout)
        run_stage(
            machine,
            [
                "cmake",
                "-S",
                ".",
                "-B",
                "build",
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DPSXPORT_DIR={psxport_path.absolute()}",
                f"-DCMAKE_C_COMPILER={cc}",
                f"-DCMAKE_CXX_COMPILER={cxx}",
            ],
            "cmake configure failed",
            root=root,
            env=environment,
            quiet=True,
        )
        run_stage(
            machine,
            ["cmake", "--build", "build", "-j", jobs, "--target", "megamanx4_port"],
            "native port build failed",
            root=root,
            env=environment,
        )
        run_stage(
            machine,
            ["ctest", "--test-dir", "build", "--output-on-failure"],
            "verification failed",
            root=root,
            env=environment,
        )
    except LauncherFailure as exc:
        print(f"{RED}[run] error:{RESET} {exc}", file=stderr)
        return 1

    launch_env = dict(environment)
    launch_env["PSXPORT_ASSET_DIR"] = str(psxport_path)
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
