#!/usr/bin/env python3
"""Positive and refusal tests for tools/run.py's shipping launcher path."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

import run

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = REPO_ROOT / "scratch" / "raw"


class FakeHost(run.Host):
    def __init__(
        self, missing: set[str] | None = None, fail_command: str | None = None
    ) -> None:
        self.missing = missing or set()
        self.fail_command = fail_command
        self.commands: list[tuple[list[str], dict[str, object]]] = []

    def which(self, name: str) -> str | None:
        return None if name in self.missing else f"/fake/{name}"

    def run(
        self, args: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        self.commands.append((command, kwargs))
        executable = Path(command[0]).name
        returncode = 1 if self.fail_command and self.fail_command in command else 0
        stdout = ""
        if command[-1:] == ["--version"]:
            stdout = "clang version 22.1.8"
        elif executable == "getconf":
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
        (self.root / "external" / "psxport" / "scripts").mkdir()
        (
            self.root / "external" / "psxport" / "scripts" / "sync-submodules.sh"
        ).write_text("#!/bin/sh\n")
        (self.root / "external" / "mmx4" / "config").mkdir(parents=True)
        (self.root / ".gitmodules").write_text("# fixture\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(self, host: FakeHost, *argv: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run.run_launcher(
            argv,
            environ={
                "CC": "clang",
                "CXX": "clang++",
                "PATH": os.environ.get("PATH", ""),
            },
            host=host,
            root=self.root,
            stdout=stdout,
            stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_positive_path_provisions_emits_builds_verifies_and_launches(self) -> None:
        host = FakeHost()
        code, stdout, stderr = self.invoke(
            host, "Mega Man X4.chd", "ignored-like-the-shell-launcher"
        )
        commands = [command for command, _ in host.commands]

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("launching Mega Man X4", stdout)
        self.assertTrue(
            any(
                command[-2:] == ["tools/extract_exe.py", "Mega Man X4.chd"]
                for command in commands
            )
        )
        self.assertFalse(
            any("ignored-like-the-shell-launcher" in command for command in commands)
        )
        self.assertTrue(
            any(command[-1:] == ["tools/ensure_recomp.py"] for command in commands)
        )
        self.assertTrue(
            any(
                command[:3] == ["cmake", "--build", "build"]
                and command[-1] == "megamanx4_port"
                for command in commands
            )
        )
        self.assertIn(["ctest", "--test-dir", "build", "--output-on-failure"], commands)
        self.assertTrue(commands[-1][0].endswith("scratch/bin/megamanx4_port"))
        launch_env = host.commands[-1][1]["env"]
        self.assertEqual(launch_env["PSXPORT_VK_WINDOW"], "1")
        self.assertNotIn("PSXPORT_VK_HEADLESS", launch_env)
        self.assertNotIn("PSXPORT_DEBUG_SERVER", launch_env)
        self.assertEqual(
            launch_env["PSXPORT_ASSET_DIR"],
            str(self.root / "external" / "psxport"),
        )

    def test_nowindow_maps_to_headless_final_sink(self) -> None:
        host = FakeHost()
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run.run_launcher(
            [],
            environ={
                "CC": "clang",
                "CXX": "clang++",
                "PATH": os.environ.get("PATH", ""),
                "PSXPORT_NOWINDOW": "1",
            },
            host=host,
            root=self.root,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        launch_env = host.commands[-1][1]["env"]
        self.assertEqual(launch_env["PSXPORT_VK_HEADLESS"], "1")
        self.assertNotIn("PSXPORT_VK_WINDOW", launch_env)

    def test_missing_required_tool_refuses_before_mutation(self) -> None:
        host = FakeHost(missing={"cmake"})
        code, stdout, stderr = self.invoke(host)

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("cmake not found", stderr)
        self.assertEqual(host.commands, [])

    def test_empty_environment_values_and_disc_use_shell_defaults(self) -> None:
        host = FakeHost()
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run.run_launcher(
            [""],
            environ={"CC": "", "CXX": "", "PSXPORT_DIR": ""},
            host=host,
            root=self.root,
            stdout=stdout,
            stderr=stderr,
        )
        commands = [command for command, _ in host.commands]

        self.assertEqual(code, 0)
        self.assertIn(["clang", "--version"], commands)
        self.assertIn(["clang++", "--version"], commands)
        self.assertTrue(
            any(command[-1:] == ["tools/extract_exe.py"] for command in commands)
        )

    def test_provision_failure_refuses_before_build(self) -> None:
        host = FakeHost(fail_command="tools/extract_exe.py")
        code, _, stderr = self.invoke(host)
        commands = [command for command, _ in host.commands]

        self.assertEqual(code, 1)
        self.assertIn("executable provisioning failed", stderr)
        self.assertFalse(
            any(command[:3] == ["cmake", "--build", "build"] for command in commands)
        )

    def test_recomp_failure_refuses_before_configure(self) -> None:
        host = FakeHost(fail_command="tools/ensure_recomp.py")
        code, _, stderr = self.invoke(host)
        commands = [command for command, _ in host.commands]

        self.assertEqual(code, 1)
        self.assertIn("recompiled substrate generation failed", stderr)
        self.assertFalse(any(command[:2] == ["cmake", "-S"] for command in commands))

    def test_shell_entry_point_is_only_an_exec_wrapper(self) -> None:
        wrapper = (REPO_ROOT / "run.sh").read_text()
        self.assertEqual(
            wrapper, '#!/bin/sh\nexec "$(dirname "$0")/tools/run.py" "$@"\n'
        )
        self.assertTrue(os.access(REPO_ROOT / "run.sh", os.X_OK))
        self.assertTrue(os.access(REPO_ROOT / "tools" / "run.py", os.X_OK))


if __name__ == "__main__":
    unittest.main()
