#!/usr/bin/env python3
"""Resolve the disc image: CLI argument, $PSXPORT_X4_DISC, .env, then a *.chd in the repo root.

Prints only the path on stdout; exits 2 naming what it tried, or when a source names a missing path.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_KEY = "PSXPORT_X4_DISC"
GENERIC_KEY = "PSXPORT_DISC"


def _from_dotenv(path):
    """Return (value, key) from .env, or (None, None)."""
    if not os.path.isfile(path):
        return None, None
    txt = open(path, encoding="utf-8", errors="replace").read()
    for key in (ENV_KEY, GENERIC_KEY):
        m = re.search(r"^[ \t]*" + key + r"[ \t]*=[ \t]*(.+?)[ \t]*$", txt, re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'"), key
    return None, None


def resolve(argv_path=None, *, verbose=False):
    """Resolve the disc. Returns the path, or raises SystemExit(2) naming what it tried."""
    tried = []

    if argv_path:
        tried.append(("CLI argument", argv_path))
    env = os.environ.get(ENV_KEY) or os.environ.get(GENERIC_KEY)
    if env:
        tried.append((f"${ENV_KEY}", env))
    dot, dotkey = _from_dotenv(os.path.join(ROOT, ".env"))
    if dot:
        tried.append((f".env ({dotkey})", dot))
    drops = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".chd"))
    for d in drops:
        tried.append(("*.chd in the repo root", os.path.join(ROOT, d)))

    for source, path in tried:
        if os.path.isfile(path):
            if verbose:
                print(f"[disc] {source}: {path}", file=sys.stderr)
            return path
        print(f"[disc] {source} names {path!r} — NO SUCH FILE", file=sys.stderr)
        raise SystemExit(2)

    print(
        "[disc] no disc image. Tried, in order: a CLI argument, "
        f"${ENV_KEY}, .env, and a *.chd in {ROOT}. "
        "Provide the game's own disc image — it is never shipped with this repo.",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    print(resolve(sys.argv[1] if len(sys.argv) > 1 else None, verbose=True))
