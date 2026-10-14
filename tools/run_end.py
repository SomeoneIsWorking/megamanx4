"""The framework's run-end report, read from a product log."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RUN_COMPLETE = re.compile(r"run complete: product_steps=(\d+) presentation_fences=(\d+)")


@dataclass(frozen=True)
class RunEnd:
    line: str
    product_steps: int
    presentation_fences: int


def read(text: str) -> RunEnd | None:
    """The run's `run complete` line; None when the run did not end through its report."""
    found = _RUN_COMPLETE.search(text)
    if found is None:
        return None
    return RunEnd(found.group(0), int(found.group(1)), int(found.group(2)))
