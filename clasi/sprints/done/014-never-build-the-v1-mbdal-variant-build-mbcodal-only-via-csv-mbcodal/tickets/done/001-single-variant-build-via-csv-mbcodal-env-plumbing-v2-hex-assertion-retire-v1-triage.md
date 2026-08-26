---
id: '001'
title: 'Single-variant build via csv-mbcodal: env plumbing, V2-hex assertion, retire
  V1 triage'
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: never-build-the-v1-mbdal-variant.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Single-variant build via csv-mbcodal: env plumbing, V2-hex assertion, retire V1 triage

## Description

`tools/make_deploy.py` builds a hex by shelling out to `pxt build`.
Because `pxt-microbit` declares `alwaysMultiVariant: true`, every build
today compiles the legacy V1 `mbdal` variant first, discards its hex,
and only then builds the `mbcodal` variant this project actually
ships. In the MakeCode cloud that waste is harmless (V1's own
hex-merge failure is tolerated and `pxt` moves on). Locally, under
`PXT_FORCE_LOCAL=1`, the same hex-merge failure is a subprocess exit
that aborts `pxt build` outright — `mbcodal` is never even attempted,
so the local Docker compile path cannot produce a hex at all.

The fix (measured and confirmed in
`clasi/issues/never-build-the-v1-mbdal-variant.md`) is
`PXT_COMPILE_SWITCHES=csv-mbcodal`, which sets `pxt-core`'s
`appTargetVariant` up front — a different mechanism from
`disablesVariants` that selects only `mbcodal` before any
variant-dependency filtering runs, so V1 is never built at all. This
ticket wires that switch into `tools/make_deploy.py`'s subprocess
environment, updates the output-path handling for the resulting
single-variant artifact, adds an assertion against the new
universal-vs-plain-V2 hex ambiguity this introduces, makes a deliberate
call on the now-unreachable V1 triage in `classify_attempt()`, and
rewrites the docs that describe the old multi-variant world. See
sprint.md's Architecture section (What Changed / Design Rationale) for
the full reasoning behind each decision below — this ticket implements
it, it does not re-derive it.

## Acceptance Criteria

- [x] `_run_pxt_build()`'s `subprocess.Popen(...)` call passes an
      explicit `env=` that always sets `PXT_COMPILE_SWITCHES=csv-mbcodal`
      (unconditionally — never overridable by the ambient environment,
      since there is no legitimate reason for this project to build
      `mbdal`) and sets `PXT_FORCE_LOCAL=1` as a **default** — honoring
      an already-set ambient `PXT_FORCE_LOCAL` if present (e.g.
      `PXT_FORCE_LOCAL=0` to opt back into the MakeCode cloud compiler)
      — rather than relying on the caller's shell to have exported
      either.
- [x] `HEX` and `HEX_TESTRIG` point at `built/binary.hex` in
      `DEPLOY`/`DEPLOY_TESTRIG` respectively, not
      `built/mbcodal-binary.hex`. No other call site
      (`flash()`, `sync()`/`sync_testrig()`, `build()`, `main()`)
      needs a literal-path change — they already reference the module
      constants.
- [x] A new pure function (e.g. `_count_universal_hex_blocks(hex_text)`)
      counts `:0400000A` occurrences in a hex file's text and is
      directly unit-testable with no I/O, mirroring the existing
      `classify_attempt()`/`_select_promoted()` pattern of separating
      pure logic from the I/O that feeds it.
- [x] `build()` calls this function on the produced hex immediately
      after a `SUCCESS` verdict, before printing/reporting the hex as
      ready, and treats a nonzero count as a hard failure (`sys.exit`
      with a message stating a universal hex was produced instead of a
      plain V2 hex — the switch did not take effect) rather than
      silently flashing the wrong artifact.
- [x] `_V1_HEXMERGE_RE` and its `BENIGN` branch are removed from
      `classify_attempt()` (see sprint.md's Design Rationale for why:
      V1 hex-merge is no longer an expected, retry-worthy shape once
      V1 never builds — it now means a configuration regression, and
      the log falls through to `UNKNOWN`, a hard failure with no
      retry, which is the correct response).
- [x] `_PACKAGING_ABORT_RE` (`TS9283`/`TS9043`/`TS9200`) is left
      unchanged — it is not V1-specific and remains a real benign-retry
      class for the single `mbcodal` build.
- [x] The module docstring's "Two traps" section keeps the
      `disablesVariants: ["mbdal"]` dead-hex warning (do not delete it
      as obsolete — it remains a real trap for anyone who reaches for
      `disablesVariants` in a top-level project; this repo's own
      `pxt.json` still declares it, correctly, for extension
      consumers), but drops the sentence tying a V1 `TS9283` error to
      it, since that consequence no longer occurs once V1 never builds.
- [x] The module docstring's "Build checkpoint triage" section drops
      the V1 hex-merge bullet from the benign-abort list and states
      plainly that V1 is no longer built at all under this script.
- [x] `tools/DESIGN.md`'s `make_deploy.py` bullet and its "Build
      checkpoint triage" section are updated to match: the
      `csv-mbcodal`/`appTargetVariant` mechanism, the `built/binary.hex`
      output path, the universal-vs-plain-V2 ambiguity and its
      assertion, the dropped V1 benign-abort bullet, the new
      `PXT_FORCE_LOCAL=1` default — while the `disablesVariants`
      dead-hex warning is preserved in the doc, not deleted.
- [x] No file outside `tools/make_deploy.py`, `tools/DESIGN.md`, and
      `tests/tools/test_make_deploy_triage.py` needs a doc update for
      this change (verified by the sprint-planner: no other living doc
      references `built/mbcodal-binary.hex`, `PXT_FORCE_LOCAL`, or
      `PXT_COMPILE_SWITCHES` — only historical `clasi/sprints/done/`
      ticket records do, and those are dated records, not standing
      instructions, left unedited).

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_make_deploy_triage.py`
  (the full suite, not just a subset — this ticket touches
  `classify_attempt()`, `_run_pxt_build()`, `build()`, and the
  module-level `HEX`/`HEX_TESTRIG` constants that several existing
  tests reference directly).
- **New tests to write**:
  - Unit tests for the new block-marker counting function: 0 markers
    (plain V2 fixture text) and 2 markers (a synthetic universal-hex
    fixture, e.g. two `:0400000A...` lines bracketing two variant
    blocks) — mirror the style of the existing synthetic-log fixtures
    at the top of `tests/tools/test_make_deploy_triage.py`.
  - An integration-level test that `build()` hard-fails (raises
    `SystemExit`) when the hex it finds has a nonzero block-marker
    count, even though `classify_attempt()` itself returned `SUCCESS` —
    analogous to the existing
    `test_build_reports_failure_when_benign_shape_recurs` test's shape.
    Note: the existing `test_build_retries_once_on_benign_then_succeeds`
    and `test_build_testrig_uses_its_own_scratch_dir_and_hex_path` tests
    monkeypatch `os.path.exists`/`os.path.getsize` but do not currently
    provide real hex *content* for `build()` to read — once the
    block-marker check reads the hex file, these two tests need either
    a real temp hex file (via `tmp_path`) containing a 0-marker fixture,
    or a monkeypatch of the new counting function directly, so they
    keep passing under the new check.
  - Repurpose `test_v1_hexmerge_failure_is_benign` (rename it, e.g.
    `test_v1_hexmerge_failure_is_now_unknown_not_benign`) to assert
    `classify_attempt(V1_HEXMERGE_LOG, hex_exists=False)` now returns
    `UNKNOWN`, not `BENIGN` — the regression pin the Design Rationale
    calls for.
- **Verification command**: `uv run pytest tests/tools/test_make_deploy_triage.py`
