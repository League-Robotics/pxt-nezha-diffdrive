---
id: '005'
title: testrig.ts dispatch fix and make_deploy.py testFiles build-hygiene
status: in-progress
use-cases:
- SUC-007
depends-on: []
github-issue: ''
issue: testfiles-are-not-type-checked-testrig-is-broken.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# testrig.ts dispatch fix and make_deploy.py testFiles build-hygiene

## Description

Closes the build-hygiene half of
`testfiles-are-not-type-checked-testrig-is-broken.md` (R-16: BLK-04 +
PY-06). Two related but independently-fixable defects:

1. **`test/testrig.ts`'s `onRunCommand` dispatch bug.** Current code:
   ```ts
   diffDrive.onRunCommand(function (name: string, n: number) {
       rigPending = n
   })
   ```
   `onRunCommand`'s second parameter is the run command's **argument**
   (`arg`, always `0` for a bare `RUN:<n>` with no second colon-part —
   which is how every command in `testrig.ts`'s own numeric vocabulary
   is sent), not the numeric verb itself. Storing it into `rigPending`
   means `rigExec(0)` runs for every command, matching no branch in
   `rigExec()` — the rig's entire numeric vocabulary (`RUN:20`..
   `RUN:54180+deg`) is a silent no-op. **Do not port the vocabulary to
   named verbs** — see `sprint.md`'s Design Rationale for why that was
   ruled out for this ticket. The fix is a one-line dispatch
   correction: parse the verb number from `name` (e.g.
   `parseInt(name)`), not from the always-zero `arg`.
2. **`make_deploy.py`'s testFiles-promotion filter silently excludes
   `testrig.ts`.** `sync()`'s filter
   (`make_deploy.py:171-172`) is `f.endswith('test.ts')` —
   `'test/testrig.ts'.endswith('test.ts')` is `False` (it ends in
   `'trig.ts'`), so `testrig.ts` is silently dropped from what the
   scratch deploy env builds/type-checks, and `testFiles` is then
   cleared to `[]` — `testrig.ts` is invisible to both the routine
   deploy build and (since nobody runs a plain root `pxt build`
   regularly) the everyday workflow. **Read the risk callout in
   `sprint.md`'s Migration Concerns before touching this filter**:
   `test.ts` and `testrig.ts` are two independent, mutually exclusive
   on-robot programs (playfield robot vs. the zeguz drum rig), each
   with its own top-level `basic.forever` loop and button handlers, and
   must never both be promoted into `files` in the same scratch build —
   that would compile both programs' top-level code into one hex. The
   fix must ensure `testrig.ts` is built/type-checked **on its own
   terms** (e.g. a second, separate scratch variant, or a
   type-check-only pass), not folded into `test.ts`'s deploy.

These two fixes should land in the same ticket/commit because this
sprint's build-checkpoint ticket (007) needs both together to actually
prove `testrig.ts` compiles clean.

## Acceptance Criteria

- [x] `test/testrig.ts`'s `onRunCommand` handler stores the parsed
      numeric verb (from `name`), not the always-zero `arg` — confirmed
      by tracing at least one documented vocabulary entry (e.g.
      `RUN:20` → `rigExec(20)` is reached, not `rigExec(0)`).
- [x] `testrig.ts`'s own numeric vocabulary (documented in its header
      comment, `RUN:20`..`RUN:54180+deg`) is otherwise **unchanged** —
      this ticket is a dispatch fix, not a vocabulary port.
- [x] `make_deploy.py`'s testFiles handling ensures `testrig.ts` is
      built/type-checked as part of some routine, automated path — it
      cannot again silently vanish the way it did before this ticket.
- [x] `test.ts` and `testrig.ts` are **not** both promoted into the
      same scratch build's `files` — confirm the flashable deploy hex
      still contains only `test.ts`'s handlers (unchanged behavior from
      before this ticket).
- [x] A real `pxt build` (via whatever mechanism this ticket adds)
      against `testrig.ts` with the dispatch fix in place compiles
      clean, with no type error.
- [x] `tests/tools/test_make_deploy_triage.py` (or a new sibling)
      covers the testFiles-handling fix: given a `pxt.json` fixture
      listing both `test.ts` and `testrig.ts` in `testFiles`, confirm
      `testrig.ts` is included in whatever gets built/type-checked.
- [x] `uv run pytest` (full suite) passes.

## Implementation Notes

- The `make_deploy.py` fix is build-tooling logic
  (`sync()`/`build()`-adjacent), not a change to the triage
  (`classify_attempt()`) itself — keep this ticket's scope to the
  testFiles-handling bug, not a broader rewrite of `make_deploy.py`.
- If a second scratch-build variant is the chosen mechanism, it does
  not need `flash()` support — this sprint's tickets never require a
  robot; a `testrig.ts`-only build/type-check pass that produces no hex
  (or a discardable one) is sufficient to satisfy this ticket's
  acceptance criteria.
- `tools/DESIGN.md`'s overlay (already drafted in `clasi/sprints/005-*/
  design/`) documents `testrig.ts`'s dispatch-bug fix and notes the
  mutual-exclusivity constraint — if the implementation ends up
  differing from what the overlay describes (e.g. a different
  mechanism than a "second scratch variant"), update the overlay copy
  and regenerate its `.diff.md` (hand-written per this sprint's own
  convention — no `generate_diffs` tool exists in this project) so it
  stays true after this sprint closes.

## C++11 Gate Coverage

Not applicable — `testrig.ts` is TypeScript/PXT, not C++; `make_deploy.py`
is Python build tooling. Neither is compiled by `test_cxx11_syntax_gate.py`.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/` — confirm no
  regression to `test_make_deploy_triage.py`'s existing coverage.
- **New tests to write**: extend `test_make_deploy_triage.py` (or add a
  sibling) for the testFiles-handling fix, per this ticket's Acceptance
  Criteria; no host test applies (this is PXT/TS + Python build
  tooling, not C++).
- **Verification command**: `uv run pytest`, plus a real
  `uv run python tools/make_deploy.py` (and whatever new invocation
  this ticket adds for `testrig.ts`) to confirm both files compile
  clean — network access to the cloud compiler required, no hardware.
