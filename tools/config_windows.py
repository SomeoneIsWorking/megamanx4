#!/usr/bin/env python3
"""Parse the exact PlatformHle window initializers from the title GameConfig."""

from __future__ import annotations

import re


def platform_hle_windows(config: str) -> tuple[list[str], list[str]]:
    """Return the source expressions in the low/high HLE window arrays."""
    arrays: list[list[str]] = []
    for field in ("windowLo", "windowHi"):
        match = re.search(rf"\.{field}\s*=\s*\{{([^}}]*)\}}", config)
        if not match:
            raise ValueError(f"GameConfig does not initialize .{field}")
        entries = [entry.strip() for entry in match.group(1).split(",")]
        if len(entries) != 2 or any(not entry for entry in entries):
            raise ValueError(f"GameConfig .{field} must contain exactly two windows")
        arrays.append(entries)
    return arrays[0], arrays[1]
