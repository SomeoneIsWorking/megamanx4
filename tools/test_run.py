#!/usr/bin/env python3
"""Hermetic positive and refusal tests for the shipping launcher."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

import run

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = REPO_ROOT / "scratch" / "raw"
LOCKED_PYTHON = "/locked/venv/bin/python"


class FakeHost(run.Host):
    def __init__(
        self,
        *,
        missing: set[str] | None = None,
        fail_command: str | None = None,
        system: str = "Linux",
        distribution: str = "fedora",
    ) -> None:
        self.missing = missing or set()
        self.fail_command = fail_command
        self.system_name = system
        self.distribution = distribution
        self.commands: list[tuple[list[str], dict[str, object]]] = []

    def which(self, name: str) -> str | None:
        if name in self.missing or Path(name).name in self.missing:
            return None
        return f"/fake/{Path(name).name}"

    def system(self) -> str:
        return self.system_name

    def linux_distribution(self) -> str:
        return self.distribution

    def run(
        self, args: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        self.commands.append((command, kwargs))
        returncode = 1 if self.fail_command and self.fail_command in command else 0
        stdout = ""
        if Path(command[0]).name == "getconf":
            stdout = "16"
        elif "rev-parse" in command:
            stdout = "abcdef12"
        return subprocess.CompletedProcess(
            command, returncode, stdout=stdout, stderr=""
        )


class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="run-selftest-", dir=SCRATCH)
        self.root = Path(self.temp.name)
        (self.root / "external" / "psxport" / "cmake").mkdir(parents=True)
        (self.root / "external" / "psxport" / "cmake" / "psxport.cmake").write_text(
            "# fixture\n"
        )
        policy = self.root / "external/psxport/tools/port/launch_environment.py"
        policy.parent.mkdir(parents=True)
        shutil.copyfile(
            REPO_ROOT / "external/psxport/tools/port/launch_environment.py", policy
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(
        self,
        host: FakeHost,
        *argv: str,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run.run_launcher(
            argv,
            environ=environment or {"PATH": os.environ.get("PATH", "")},
            host=host,
            root=self.root,
            python_executable=LOCKED_PYTHON,
            stdout=stdout,
            stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def command_list(host: FakeHost) -> list[list[str]]:
        return [command for command, _ in host.commands]

    def test_default_provisions_builds_and_launches(self) -> None:
        host = FakeHost()
        code, stdout, stderr = self.invoke(host, "Mega Man X4.chd")
        commands = self.command_list(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("launching Mega Man X4", stdout)
        self.assertIn([LOCKED_PYTHON, "tools/psxport_sync.py", "--auto"], commands)
        self.assertIn(
            [LOCKED_PYTHON, "tools/extract_exe.py", "Mega Man X4.chd"], commands
        )
        self.assertIn([LOCKED_PYTHON, "-B", "tools/ensure_recomp.py"], commands)
        self.assertTrue(commands[-1][0].endswith("scratch/bin/megamanx4_port"))
        self.assertFalse(
            any(command and Path(command[0]).name == "ctest" for command in commands)
        )

        configure_index = next(
            index
            for index, command in enumerate(commands)
            if command[:2] == ["cmake", "-S"]
        )
        configure, kwargs = host.commands[configure_index]
        self.assertEqual(configure[4], "scratch/build/player")
        self.assertIn("-DBUILD_TESTING=OFF", configure)
        self.assertIn(f"-DPython3_EXECUTABLE={LOCKED_PYTHON}", configure)
        self.assertIn("-DCMAKE_C_COMPILER=clang", configure)
        self.assertIn("-DCMAKE_CXX_COMPILER=clang++", configure)
        self.assertNotIn("stdout", kwargs)

    def test_prepare_only_builds_without_launching(self) -> None:
        host = FakeHost()
        code, stdout, stderr = self.invoke(host, "--prepare-only")
        commands = self.command_list(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("built and ready", stdout)
        self.assertTrue(
            any(
                command[:3] == ["cmake", "--build", "scratch/build/player"]
                for command in commands
            )
        )
        self.assertFalse(
            any(
                command and command[0].endswith("megamanx4_port")
                for command in commands
            )
        )

    def test_player_exec_strips_ambient_agent_policy(self) -> None:
        host = FakeHost()
        code, _, stderr = self.invoke(
            host,
            environment={
                "PATH": os.environ.get("PATH", ""),
                "PSXPORT_NOWINDOW": "1",
                "PSXPORT_VK_HEADLESS": "1",
                "PSXPORT_NOAUDIO": "1",
                "PSXPORT_NOPACE": "1",
            },
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        launch_env = host.commands[-1][1]["env"]
        self.assertEqual(launch_env["PSXPORT_VK_WINDOW"], "1")
        for key in ("PSXPORT_NOWINDOW", "PSXPORT_VK_HEADLESS", "PSXPORT_NOAUDIO", "PSXPORT_NOPACE"):
            self.assertNotIn(key, launch_env)

    def test_missing_cmake_prints_exact_fedora_command_before_mutation(self) -> None:
        host = FakeHost(missing={"cmake"})
        code, stdout, stderr = self.invoke(host)

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("sudo dnf install cmake", stderr)
        self.assertEqual(host.commands, [])

    def test_missing_sdl3_prints_exact_debian_command(self) -> None:
        host = FakeHost(fail_command="sdl3", distribution="ubuntu")
        code, _, stderr = self.invoke(host)

        self.assertEqual(code, 1)
        self.assertIn("sudo apt install libsdl3-dev", stderr)

    def test_missing_tools_print_platform_specific_commands(self) -> None:
        cases = (
            (FakeHost(missing={"git"}), "sudo dnf install git"),
            (
                FakeHost(missing={"pkg-config"}, distribution="debian"),
                "sudo apt install pkg-config",
            ),
            (
                FakeHost(missing={"cmake"}, system="Darwin"),
                "brew install cmake",
            ),
        )
        for host, command in cases:
            with self.subTest(command=command):
                code, _, stderr = self.invoke(host)
                self.assertEqual(code, 1)
                self.assertIn(command, stderr)

    def test_clang_is_preferred_when_no_compiler_is_configured(self) -> None:
        host = FakeHost()
        code, _, stderr = self.invoke(host, "--prepare-only")
        commands = self.command_list(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        configure = next(
            command for command in commands if command[:2] == ["cmake", "-S"]
        )
        self.assertIn("-DCMAKE_C_COMPILER=clang", configure)
        self.assertIn("-DCMAKE_CXX_COMPILER=clang++", configure)

    def test_cmake_discovers_the_compiler_when_clang_is_absent(self) -> None:
        host = FakeHost(missing={"clang", "clang++"})
        code, _, stderr = self.invoke(host, "--prepare-only")
        commands = self.command_list(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        configure = next(
            command for command in commands if command[:2] == ["cmake", "-S"]
        )
        self.assertFalse(
            any(option.startswith("-DCMAKE_C_COMPILER=") for option in configure)
        )
        self.assertFalse(
            any(option.startswith("-DCMAKE_CXX_COMPILER=") for option in configure)
        )

    def test_explicit_compilers_are_passed_through_without_identity_checks(
        self,
    ) -> None:
        host = FakeHost()
        code, _, stderr = self.invoke(
            host,
            "--prepare-only",
            environment={"CC": "custom-c", "CXX": "custom-cxx"},
        )
        configure = next(
            command
            for command in self.command_list(host)
            if command[:2] == ["cmake", "-S"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("-DCMAKE_C_COMPILER=custom-c", configure)
        self.assertIn("-DCMAKE_CXX_COMPILER=custom-cxx", configure)

    def test_one_sided_compiler_override_is_left_for_cmake(self) -> None:
        host = FakeHost()
        code, _, stderr = self.invoke(host, environment={"CC": "gcc"})
        configure = next(
            command
            for command in self.command_list(host)
            if command[:2] == ["cmake", "-S"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("-DCMAKE_C_COMPILER=gcc", configure)
        self.assertFalse(
            any(option.startswith("-DCMAKE_CXX_COMPILER=") for option in configure)
        )

    def test_explicit_framework_checkout_skips_auto_sync(self) -> None:
        host = FakeHost()
        framework = self.root / "framework-dev"
        (framework / "cmake").mkdir(parents=True)
        (framework / "cmake" / "psxport.cmake").write_text("# fixture\n")
        code, _, stderr = self.invoke(
            host,
            "--prepare-only",
            environment={"PSXPORT_DIR": str(framework)},
        )
        commands = self.command_list(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn([LOCKED_PYTHON, "tools/psxport_sync.py", "--auto"], commands)
        provision_index = commands.index([LOCKED_PYTHON, "tools/extract_exe.py"])
        self.assertEqual(
            host.commands[provision_index][1]["env"]["PSXPORT_DIR"], str(framework)
        )

    def test_provision_failure_refuses_before_build(self) -> None:
        host = FakeHost(fail_command="tools/extract_exe.py")
        code, _, stderr = self.invoke(host)
        commands = self.command_list(host)

        self.assertEqual(code, 1)
        self.assertIn("executable provisioning failed", stderr)
        self.assertFalse(
            any(command[:2] == ["cmake", "--build"] for command in commands)
        )

    def test_shell_and_locked_project_are_the_stable_entry_contract(self) -> None:
        wrapper = (REPO_ROOT / "run.sh").read_text()
        bootstrap = (REPO_ROOT / "bootstrap.py").read_text()
        project = (REPO_ROOT / "pyproject.toml").read_text()
        lock = (REPO_ROOT / "uv.lock").read_text()

        self.assertEqual(
            wrapper,
            '#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec uv run --frozen python bootstrap.py "$@"\n',
        )
        self.assertIn("from tools.run import main", bootstrap)
        self.assertIn("package = false", project)
        self.assertIn("version = 1", lock)
        self.assertTrue(os.access(REPO_ROOT / "run.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
