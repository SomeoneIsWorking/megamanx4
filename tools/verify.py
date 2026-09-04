#!/usr/bin/env python3
"""Run Mega Man X4's complete asset-free Linux product gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PSXPORT = ROOT / "external" / "psxport"


def main() -> int:
    bootstrap = subprocess.run(
        [sys.executable, ROOT / "tools" / "psxport_sync.py", "--auto"],
        cwd=ROOT,
        check=False,
    )
    if bootstrap.returncode:
        print(f"[verify] FAILED: PSXPort bootstrap exited {bootstrap.returncode}", file=sys.stderr)
        return bootstrap.returncode

    sys.path.insert(0, str(PSXPORT / "tools"))
    from port.consumer_verify import ConsumerVerifyConfig, run_consumer_verification

    build = ROOT / "build" / "ci"
    return run_consumer_verification(
        ConsumerVerifyConfig(
            name="Mega Man X4",
            root=ROOT,
            build=build,
            psxport=PSXPORT,
            product=build / "bin" / "megamanx4_port",
            cmake_module=ROOT / "cmake" / "megamanx4_port.cmake",
            test_regex=(
                r"^(cpp_policy|launcher_policy|no_temporal_source_dependency|"
                r"x4_.*|no_temporal_binary_dependency)$"
            ),
            cmake_definitions=("-DBUILD_TESTING=ON", "-DPSXPORT_BUILD_SMOKE=OFF"),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
