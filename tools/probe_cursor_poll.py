#!/usr/bin/env python3
"""Poll one guest word at high frequency and histogram the values it actually takes.

WHY THIS EXISTS. MMX4's guest scheduler (`0x80012600`) stores `$v0` into the cursor at
`0x801F8300` (`0x80012628`), then walks the cursor forward by `0x80` per pass and stores it
again at `0x80012724` until it reaches `0x801F8380`. Decoded from the authenticated image,
that means **the cursor must take the value `0x801F8380` between calls** — yet every earlier
sampling of this word reported `0x801F8300`, the self-reference, every single time.

Those two facts cannot both hold. Which of them is wrong is the question, and it decides
whether the fault is a data problem or a code problem.

WHY NOT THE STORE OBSERVER. `psxport/docs/issues/0039` measured that arming
`PSXPORT_STORE_OBSERVE` invalidates every compiled block and instruments every store in
every block, so a run with it armed **is not the program**. It cannot settle this.

SO: this polls the word as fast as the endpoint allows and reports the FULL HISTOGRAM of
what it saw. The histogram is the point. A single reported value is exactly the failure this
project keeps meeting — a confident answer about the wrong subject — and only a spread of
observed values can distinguish "the cursor only ever holds X" from "we keep sampling in one
window".

WHAT WOULD SETTLE IT, both directions, named in the output:
  * `0x801F8380` appears -> `0x80012724` executes, and the earlier single-value readings were
    sampled in the narrow window right after `0x80012628`.
  * only `0x801F8300` appears, over a large sample -> `0x80012724` does NOT execute despite
    the static trace, which is a code/translation problem rather than a data one.
"""

from __future__ import annotations

import collections
import socket
import sys
import time

DEFAULT_ADDRESS = 0x801F8300
MIN_SAMPLES = 200
# The value the decoded path at 0x80012724 MUST store, and the self-reference that is
# actually observed. Named once so the tool, its prediction and its selftest cannot drift
# apart silently.
PREDICTED_CURSOR = 0x801F8380
OBSERVED_SELF_REFERENCE = 0x801F8300


def parse_port(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        raise SystemExit(0)
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        raise SystemExit("usage: probe_cursor_poll.py PORT [ADDRESS_HEX]")
    return int(args[0])


def parse_address(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    return int(args[1], 16) if len(args) > 1 else DEFAULT_ADDRESS


class Endpoint:
    def __init__(self, port: int) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5.0)
        self.buf = b""

    def cmd(self, text: str) -> str | None:
        try:
            self.sock.sendall((text + "\n").encode())
        except OSError:
            return None
        deadline = time.time() + 5.0
        while b"\n" not in self.buf and time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            self.buf += chunk
        if b"\n" not in self.buf:
            return None
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode(errors="replace").strip()

    def word(self, address: int) -> int | None:
        reply = self.cmd(f"rw {address:X} 1")
        if reply is None or ":" not in reply:
            return None
        try:
            return int(reply.split(":", 1)[1].split()[0], 16)
        except (IndexError, ValueError):
            return None


def classify(seen: "collections.Counter[int]", reads: int, failures: int) -> tuple[str, int]:
    """Decide the verdict from a histogram. Pure: no I/O, no clock, no defaults.

    EVERY refusal and EVERY verdict lives here and nowhere else, so the selftest can drive
    this function with synthetic histograms and a mutation to a decision becomes observable.

    That separation is not decoration. The first version of this tool decided inline in
    `main` and its selftest compared constants — three behavioural mutations to the refusals
    all survived, which is a gate that cannot fail, and a gate that cannot fail is not a gate.
    """
    observed = sum(seen.values())
    print(f"scanned {reads} read(s); {failures} returned nothing; {observed} carried a value")
    # Order matters for testability, not just tidiness: an empty histogram is also below the
    # floor, so checking the floor first made this branch unreachable and a mutation removing
    # it survived. The all-failed case is the more informative message, so it goes first and
    # both guards stay live.
    if not seen:
        return ("REFUSED: every read failed; there is no measurement here", 1)
    if observed < MIN_SAMPLES:
        return (f"REFUSED: only {observed} usable sample(s), below the {MIN_SAMPLES} needed to "
                f"claim the word is constant. A short run proves nothing about a polling phase, "
                f"and reporting one is a green zero.", 1)

    print(f"{len(seen)} distinct value(s) observed:")
    for value, count in seen.most_common(8):
        print(f"  0x{value:08X}  {count:>6} read(s)  {100.0 * count / observed:5.1f}%")

    if PREDICTED_CURSOR in seen:
        return (f"VERDICT: 0x{PREDICTED_CURSOR:08X} WAS observed in {seen[PREDICTED_CURSOR]} "
                f"read(s) - the cursor store at 0x80012724 executes, and the earlier single-value "
                f"readings were sampling one narrow window.", 0)
    if len(seen) == 1:
        only = next(iter(seen))
        return (f"VERDICT: only 0x{only:08X} was observed over {observed} read(s). The decoded "
                f"path says 0x80012724 must store 0x{PREDICTED_CURSOR:08X}, so the data and the "
                f"code disagree - a code/translation problem, not a data one.", 0)
    return ("VERDICT: more than one value and not the one the trace predicts; the window this "
            "polls in has not been characterised. NOT a conclusion.", 0)


def selftest() -> int:
    """Drive `classify` with synthetic histograms, covering every refusal and both verdicts.

    These are the tool's actual decisions, so a mutation to `classify` turns this red. If a
    mutation survives, the gate is decorative and must be rewritten rather than trusted.
    """
    cases: list[tuple[str, "collections.Counter[int]", int, int, int, str]] = [
        ("no usable sample is refused",
         collections.Counter(), 400, 400, 1, "REFUSED"),
        ("one sample below the floor is refused",
         collections.Counter({OBSERVED_SELF_REFERENCE: 1}), 5, 4, 1, "REFUSED"),
        # This one must name WHICH guard fired. Asserting only "REFUSED" passes whether the
        # all-failed guard or the floor guard handled it, so a mutation removing the specific
        # guard survived until this was tightened - which is the whole point of a mutation
        # check rather than a shape check.
        ("an empty histogram is the all-failed refusal, not the short-run one",
         collections.Counter(), MIN_SAMPLES + 10, 0, 1, "every read failed"),
        ("a short-but-present run is the floor refusal, not the all-failed one",
         collections.Counter({OBSERVED_SELF_REFERENCE: 3}), MIN_SAMPLES + 10, 0, 1,
         "below the 200 needed"),
        ("only the self-reference is the code/data-disagreement verdict",
         collections.Counter({OBSERVED_SELF_REFERENCE: 5000}), 5000, 0, 0,
         "code/translation problem"),
        ("the predicted value appearing is the other verdict",
         collections.Counter({OBSERVED_SELF_REFERENCE: 100, PREDICTED_CURSOR: 4000}), 4100, 0, 0,
         "0x80012724 executes"),
        ("an uncharacterised spread refuses to conclude",
         collections.Counter({0x11111111: 2000, 0x22222222: 2000}), 4000, 0, 0,
         "NOT a conclusion"),
    ]
    failures: list[str] = []
    for name, seen, reads, failed, want_rc, want_text in cases:
        got_text, got_rc = classify(seen, reads, failed)
        if got_rc != want_rc:
            failures.append(f"{name}: exit {got_rc}, expected {want_rc}")
        if want_text not in got_text:
            failures.append(f"{name}: text lacks {want_text!r}; got {got_text[:70]!r}")

    # The discrimination the whole tool exists for: the two verdicts must be reachable
    # separately, and the predicted value must not equal the value always observed, or the
    # verdict could never fire and the tool would always report the same thing.
    if PREDICTED_CURSOR == OBSERVED_SELF_REFERENCE:
        failures.append("PREDICTED_CURSOR equals OBSERVED_SELF_REFERENCE; no verdict can fire")
    if PREDICTED_CURSOR != 0x801F8380:
        failures.append("PREDICTED_CURSOR no longer names the value the decoded trace predicts")

    for line in failures:
        print(f"SELFTEST FAIL: {line}")
    if failures:
        return 1
    print(f"selftest passed: {len(cases)} decision cases, and the two verdicts are distinct")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    port = parse_port(argv)
    address = parse_address(argv)
    try:
        endpoint = Endpoint(port)
    except OSError as exc:
        print(f"REFUSED: cannot reach the debug endpoint on 127.0.0.1:{port} ({exc})")
        return 2

    seen: collections.Counter[int] = collections.Counter()
    reads = 0
    failures = 0
    started = time.time()
    while time.time() - started < 12.0:
        value = endpoint.word(address)
        reads += 1
        if value is None:
            failures += 1
        else:
            seen[value] += 1
        if reads % 2000 == 0:
            print(f"  polled {reads} read(s), {len(seen)} distinct value(s)", flush=True)

    text, code = classify(seen, reads, failures)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
