# Project goals

Mega Man X4 is an enhancement-class PC port of the USA `SLUS_005.61` release. These goals record
durable product outcomes; factual delivery coverage lives in `docs/project-state.md`.

## G001 — Playable faithful PC product

Deliver the retail game as one native/Lightrec psxport product built from user-supplied disc data,
with its guest GTE picture, input, audio, saves, timing, and game behavior intact. The authenticated
executable remains runtime data: native overrides own selected verified functions and Lightrec
dynamically executes every remaining guest instruction.

Success means the default launcher provisions and starts the actual product, and representative
front-end and gameplay sessions are inspected as well as tested. Supported player choices are
truthful: the port does not expose modes it does not implement. The gameplay product executes
nonzero Lightrec blocks and routes native overrides and scoped original calls through its shipping
dispatcher. The dynarec remains the default; the product has no player-selectable interpreter mode.

Contributing state: S001, S002, S003, S004, S005, S009, S010.

## G002 — True widescreen

Extend the game's own projection, visibility, edge coverage, and 2D layout to wide aspect ratios
while retaining an exact faithful 4:3 path.

Success requires additional correctly composed content rather than stretching or shifting the
320-pixel composition. Matched title and gameplay captures must preserve the central scale and show
semantically correct margins.

Contributing state: S004, S006.

## G003 — Loading removal

Remove storage latency and loading-only waits without changing unrelated scripted timing or using a
presentation workaround.

Success requires each measured load operation to deliver the same payload and terminal state while
omitting its loading presentation. Non-loading fades and timers remain retail behavior until they are
independently classified.

Contributing state: S007.

## G004 — Drop-in co-op

Allow a second player to join during play as the other hunter, with independent input and correct
player, camera, collision, combat, checkpoint, and lifecycle behavior.

Success includes an explicit co-op evidence strategy because the enhanced two-player state cannot be
byte-compared with the single-player retail oracle.

Contributing state: S003, S008.

## Constraints and non-goals

- Native rendering, native graphics producers, native depth, interpolation/lerp, and a synthetic
  60fps mode are out of scope. The retail game already owns its target cadence and guest GTE picture.
- The player interface exposes none of those unsupported modes. Diagnostic software rasterization
  may remain an explicit maintainer path; it is not a player renderer choice.
- Widescreen, fast loading, and co-op remain suppressed under oracle/SBS comparison.
- AGPL-derived Mega Man X4 code stays inside this repository and never enters psxport.
- Provisioning validates runtime data and never emits executable code. Runtime JIT output is
  disposable user data, never an install input.
- Forced interpretation may exist only in a separately built test/diagnostic target. Lightrec may
  use its bounded automatic interpreter fallback only for a JIT-refused block. Per-reason and
  instruction telemetry plus an enforced release threshold must keep fallback exceptional rather
  than becoming a disguised gameplay engine.
