---
id: '001'
title: 'Harden make_deploy.py''s build gate: hex size floor and translation-unit presence
  check'
status: done
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: make-deploy-accepts-a-silently-incomplete-hex.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Harden make_deploy.py's build gate: hex size floor and translation-unit presence check

## Description

`tools/make_deploy.py`'s `build()` judges a build attempt success purely
from `classify_attempt()`'s log-based triage plus hex existence. A stale
vendored `codal-microbit-v2` checkout produced a `binary.hex` 27% short
(1,046,410 vs 1,442,546 bytes) with a clean exit status and nothing in
the log to flag it (sprint 016 ticket 007). The same class of failure —
a build served entirely from a stale cache, compiling nothing — has
recurred at least four times (sprints 016, 018, 022, and again on
2026-08-26), each time producing a build with **zero**
`Building CXX object` lines that still passed.

Add two post-build assertions to `build()` in `tools/make_deploy.py`,
following the existing `classify_attempt()` /
`_count_universal_hex_blocks()` pattern: pure functions, unit-tested
against synthetic/saved text, no subprocess:

1. **A size floor on `binary.hex`.** Add a named constant
   `MIN_HEX_SIZE_BYTES` with a comment recording the measured
   checkpoints beside it (1,423,241 / sprint 014, 1,434,671 / sprint
   015, 1,442,546 / sprint 016, and any more recent checkpoint the
   implementer can find — the planning-time read of the issue cites a
   1,423,241–1,463,606 byte band). Suggested starting value: **1,300,000
   bytes** (~1.24 MiB) — roughly 120 KB above the 1,046,410-byte
   truncated hex that exposed this gap, and roughly 120 KB below the low
   end of the measured band. Confirm this value against the current
   measured band before landing it (Open Question 2 in `sprint.md`'s
   Architecture section) rather than taking it as fixed.
2. **A translation-unit presence check.** All ten `nezha-diffdrive`
   `.cpp` files must appear as `Building CXX object` lines in the
   captured build output:
   `src/comms/protocol.cpp`, `src/comms/radio_transport.cpp`,
   `src/comms/serial_transport.cpp`, `src/comms/wire_adapter.cpp`,
   `src/comms/wire_handler.cpp`, `src/core/diffdrive.cpp`,
   `src/motion/motion_engine.cpp`, `src/platform/nezha_port.cpp`,
   `src/platform/otos_port.cpp`, `src/shims.cpp`. The real log line
   shape (confirmed against sprint 016 ticket 007's captured build
   evidence) is:
   `[ 93%] Building CXX object CMakeFiles/MICROBIT.dir/pxtapp/nezha-diffdrive/src/comms/protocol.cpp.obj`.
   **A build output containing zero `Building CXX object` lines must
   fail this check exactly like any other missing subset** — do not
   special-case "nothing compiled" as "nothing needed rebuilding,
   therefore fine." This is the specific shape that has recurred three
   times already and must not slip through again via an
   `if compiled_count == 0: skip check` shortcut.

Both checks run inside `build()` after the existing universal-hex-block
check, before a hex is ever printed as ready to flash. On failure, exit
the same way an `UNKNOWN`/`HARD_FAILURE` triage verdict does today
(`sys.exit` with a specific, actionable reason naming what was expected
vs. found).

Explicitly out of scope (per the issue): detecting a stale vendored
checkout by comparing the resolved `dockercodal` revision against the
`codal.json` pin. Do not implement that here.

## Acceptance Criteria

- [x] `MIN_HEX_SIZE_BYTES` is a named constant in `tools/make_deploy.py`
      with the measured-checkpoint band recorded in a comment beside it.
- [x] `build()` fails with a specific, actionable message when
      `binary.hex` exists but is smaller than `MIN_HEX_SIZE_BYTES`.
- [x] `build()` fails with a specific, actionable message naming which
      of the ten `nezha-diffdrive` `.cpp` files are missing from the
      captured build output's `Building CXX object` lines.
- [x] A build output with **zero** `Building CXX object` lines fails the
      same way (covered by its own test, not incidentally by the
      missing-files test).
- [x] A genuine clean-build fixture (all ten files present, hex at or
      above the floor) still passes `build()` — proving the new checks
      don't false-positive on a real success.
- [x] Both new checks are pure functions (no subprocess, no real build)
      matching `classify_attempt()` / `_count_universal_hex_blocks()`'s
      existing testability pattern.
- [x] `tools/DESIGN.md`'s "Build checkpoint triage" section (referenced
      by `build()`'s own docstring/comments) is updated to describe the
      two new checks alongside the existing universal-hex-block check.

## Implementation Plan

**Approach**: Mirror the existing triage functions' shape exactly.
Something like `_check_hex_size(hex_path, floor=MIN_HEX_SIZE_BYTES)` and
`_check_translation_units(output, expected_files=EXPECTED_CPP_FILES)`
(names at the implementer's discretion), each returning enough
information for `build()` to construct a specific failure message (e.g.
a list of missing files, or the actual vs. expected byte count). Wire
both into `build()` right after the existing
`_count_universal_hex_blocks()` check, in the same
`if ...: sys.exit(...)` style already used there.

**Files to modify**:
- `tools/make_deploy.py` — add `MIN_HEX_SIZE_BYTES`, the expected
  ten-file list (or derive it from a constant list matching `find src
  -name '*.cpp'`'s current output — keep it a literal list, not a
  filesystem scan at check time, so the check still catches "this repo
  grew an 11th `.cpp` file nobody told the gate about" as a mismatch
  worth noticing, not silently expanding to match), the two check
  functions, and their call sites inside `build()`.
- `tools/DESIGN.md` — extend the "Build checkpoint triage" section
  (or equivalent) to document the two new checks, matching how the
  universal-hex-block check is already documented there.

**Files to create**:
- None required, but add new test functions to the existing
  `tests/tools/test_make_deploy_triage.py` rather than a new file,
  matching how `_count_universal_hex_blocks()`'s tests were added
  alongside `classify_attempt()`'s.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` (scoped to
  the tools test suite this ticket touches, per the project's
  scoped-run convention for ticket work).
- **New tests to write** (in `tests/tools/test_make_deploy_triage.py`):
  - Size-floor check: hex below `MIN_HEX_SIZE_BYTES` fails; hex at/above
    it passes.
  - Translation-unit check: build output missing one file fails, naming
    that file; build output missing several files fails, naming all of
    them; build output with **zero** `Building CXX object` lines fails
    (its own explicit test, not just a degenerate case of the
    missing-files test); a build output containing all ten files (using
    the real log line shape above) passes.
  - Positive/regression test: a synthetic "genuine clean build" fixture
    (all ten `Building CXX object` lines, hex size at/above the floor)
    still reaches `build()`'s success path — proving the new checks
    don't regress the happy path `test_build_retries_once_on_benign_
    then_succeeds` and friends already cover.
- **Verification command**: `uv run pytest tests/tools/` and
  `uvx ruff check tools tests`.

## Implementation Notes

**`MIN_HEX_SIZE_BYTES` confirmed at the planning-time suggestion,
1,300,000 bytes (Open Question 2).** Re-searched the sprint history for
every measured `built/binary.hex` size at a build checkpoint: 1,423,241
/ 1,434,671 / 1,442,546 / 1,442,996 / 1,448,621 / 1,463,606 / 1,463,516
bytes — measured low 1,423,241, measured high 1,463,606, matching the
band cited in the issue/ticket almost exactly (the issue's own
1,423,241–1,463,606 range). The band has not shifted meaningfully since
the planning-time read, so 1,300,000 stands: ~123 KB below the band's
low end, ~254 KB above the 1,046,410-byte truncated hex that exposed
this gap. Recorded as a comment beside the constant in
`tools/make_deploy.py` (without sprint/ticket numbers per this
project's comment-archaeology convention — the byte-value history is
the load-bearing fact, not which sprint measured it).

**Zero-`Building CXX object`-lines handling.** `_check_translation_units()`
is written as "is each of the ten known files found in the output",
never the reverse ("is each found line one of the ten") — the latter
is vacuously true on an empty found-set, which is exactly the stale-
cache defect shape. No special-casing was added for the zero-lines
case; it naturally falls out of the same expected-found check (all ten
come back missing), and is covered by its own dedicated test
(`test_check_translation_units_zero_lines_reports_all_ten_missing` and
`test_build_fails_when_zero_translation_units_compiled`) rather than
relying on the missing-file test to cover it incidentally, per the
ticket's own acceptance criterion.

**Recovery message.** Both new failure messages name the stale scratch
directory explicitly (derived from `hex_path`, so it is correct for
both the primary deploy and `--testrig`) and instruct
`shutil.rmtree(<dir>)` via Python, noting `rm -rf` may be
sandbox-denied, per the ticket's own instruction.
