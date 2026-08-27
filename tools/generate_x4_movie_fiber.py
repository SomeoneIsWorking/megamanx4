#!/usr/bin/env python3
"""Derive X4's resumable movie bodies from the local recompiled retail executable.

The generated substrate remains untracked and unchanged. This tool copies the three measured movie
bodies into the build tree and replaces exactly their authenticated libetc VSync calls with the
title-owned BIOS-thread field-yield seam. The original generated bodies remain linked as supers.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


FUNCTIONS = {
    "80018000": ("x4_native_general_movie", ("8001810C",)),
    "800182E8": ("x4_native_capcom_movie", ("8001842C", "800185D8")),
    "80018B88": ("x4_native_movie_frame", ("80018BC4",)),
}


def extract_function(sources: list[str], address: str) -> str:
    marker = f"void gen_func_{address}(Core* c) {{"
    matches: list[str] = []
    for source in sources:
        start = source.find(marker)
        if start < 0:
            continue
        next_function = source.find("\nvoid gen_func_", start + len(marker))
        if next_function < 0:
            raise ValueError(f"generated function {address} has no following body boundary")
        matches.append(source[start:next_function].rstrip() + "\n")
    if len(matches) != 1:
        raise ValueError(f"expected one generated body for {address}, found {len(matches)}")
    return matches[0]


def transform_function(body: str, address: str) -> str:
    native_name, expected_returns = FUNCTIONS[address]
    marker = f"void gen_func_{address}(Core* c) {{"
    body = body.replace(marker, f"void {native_name}(Core* c) {{", 1)
    call_pattern = re.compile(
        r"c->r\[31\] = 0x(?P<return>[0-9A-F]{8})u;(?P<middle>[^\n]*\n[^\n]*?)"
        r"func_800E4DB0\(c\);"
    )
    observed: list[str] = []

    def replace_call(match: re.Match[str]) -> str:
        return_address = match.group("return")
        observed.append(return_address)
        return (
            f"c->r[31] = 0x{return_address}u;{match.group('middle')}"
            f"x4::movie::yieldField(c, 0x{return_address}u);"
        )

    body = call_pattern.sub(replace_call, body)
    if tuple(observed) != expected_returns:
        raise ValueError(
            f"movie {address} VSync boundary drift: expected {expected_returns}, "
            f"observed {tuple(observed)}"
        )
    if "func_800E4DB0(c)" in body:
        raise ValueError(f"movie {address} retains an unowned VSync call")
    return body


def generate(sources: list[str]) -> str:
    bodies = [
        transform_function(extract_function(sources, address), address)
        for address in FUNCTIONS
    ]
    preamble = """// Generated at build time from the user's local recompiled SLUS_005.61 substrate.
// Do not edit: tools/generate_x4_movie_fiber.py owns this derivative.
#include "core.h"
#include "movie_field.h"
#include "rec_decls.h"

"""
    return preamble + "\n".join(bodies)


def selftest() -> None:
    sources = []
    for address, (_, returns) in FUNCTIONS.items():
        calls = "\n".join(
            f"  c->r[31] = 0x{return_address}u;\n"
            "  c->r[4] = c->r[0]; rec_guest_instruction_ticks(c, 2u); func_800E4DB0(c);"
            for return_address in returns
        )
        sources.append(
            f"void gen_func_{address}(Core* c) {{\n{calls}\n}}\n\n"
            f"void gen_func_F{address[1:]}(Core* c) {{\n}}\n"
        )
    result = generate(sources)
    assert result.count("movie::yieldField") == 4
    assert "func_800E4DB0(c)" not in result
    for native_name, _ in FUNCTIONS.values():
        assert f"void {native_name}" in result

    changed = sources.copy()
    changed[1] = changed[1].replace("8001842C", "80018430")
    try:
        generate(changed)
    except ValueError as error:
        assert "boundary drift" in str(error)
    else:
        raise AssertionError("changed movie field return was accepted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.selftest:
        selftest()
        return 0
    if args.generated_dir is None or args.output is None:
        raise ValueError("--generated-dir and --output are required unless --selftest is used")
    sources = [
        path.read_text(encoding="utf-8")
        for path in sorted(args.generated_dir.glob("shard_*.c"))
    ]
    if not sources:
        raise ValueError(f"no generated shards found under {args.generated_dir}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate(sources), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"generate_x4_movie_fiber: {error}", file=sys.stderr)
        raise SystemExit(1)
