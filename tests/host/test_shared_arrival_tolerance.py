"""tests/host/test_shared_arrival_tolerance.py -- sprint 032 ticket 008.

Before this ticket, `world.ts` owned `arriveTolCm` (settable via
`setArrivalTolerance()`) and used it only for `goToWorld()`'s own
JS-level pre-check; `motion.ts`'s `startGoTo()` hardcoded
`const goalArrive = 1` (mm) into its own `_goToR(...)` call regardless
of what `setArrivalTolerance()` was ever called with. Calling
`setArrivalTolerance(3)` changed `goToWorld`'s pre-check but had ZERO
effect on the underlying `_goToR` call either go-to block ultimately
makes.

The fix moves the shared state (renamed `arriveTol`, unit-free per
`.claude/rules/no-units-in-identifiers.md` -- the unit lives in a
trailing `// [cm]` comment on the declaration) to `motion.ts`, the
lower layer both files already depend on for their tick runner
(`move()`/`goTo()`), and has `startGoTo()` thread it into `_goToR`'s
`arrive` parameter. `world.ts` no longer declares its own copy or its
own `setArrivalTolerance()` block. `arriveTol` itself stays an
unexported `let` (same visibility as motion.ts's sibling
`defaultSpeed`/`defaultYawRate` state) -- TypeScript's cross-file
namespace merging shares EXPORTED members by bare identifier, not
plain `let`s, so `world.ts` reads it through a new one-line exported
accessor, `arrivalTolerance()`, rather than a second declaration.

**Why source-pinning, not a behavioral run.** `tests/host/` cannot
compile or execute this package's TypeScript/PXT layer at all (see
`test_run_abort_source_pin.py`'s own docstring for the same
limitation) -- there is no host build of `blocks/motion.ts`/
`blocks/world.ts` to drive a real `setArrivalTolerance()` call through
and observe the two go-to blocks agree. This file instead pins the
SOURCE SHAPE that makes agreement possible by construction: one
declaration site, one setter, and both go-to code paths reading the
identical identifier -- so a future edit that reintroduces a second,
independent copy (the exact defect this ticket fixes) fails here
instead of silently reaching a student.

Run with::

    uv run pytest tests/host/test_shared_arrival_tolerance.py
"""

import pathlib
import re

# tests/host/test_shared_arrival_tolerance.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_MOTION_TS = _REPO_ROOT / "src" / "blocks" / "motion.ts"
_WORLD_TS = _REPO_ROOT / "src" / "blocks" / "world.ts"


def _motion_ts_source() -> str:
    return _MOTION_TS.read_text(encoding="utf-8")


def _world_ts_source() -> str:
    return _WORLD_TS.read_text(encoding="utf-8")


def _find_balanced_close(text: str, open_brace_idx: int) -> int:
    depth = 0
    i = open_brace_idx
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces starting at %d" % open_brace_idx)


def _function_body(name: str, src: str) -> str:
    m = re.search(r"function\s+%s\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{" %
                  re.escape(name), src)
    assert m, "function %s() not found" % name
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.end():close_idx - 1]


def test_arrive_tol_declared_once_in_motion_ts():
    """The shared arrival-tolerance state lives in motion.ts (the lower
    layer), not world.ts -- per sprint.md's dependency-direction
    decision for this sprint's tick-runner consolidation."""
    motion_src = _motion_ts_source()
    assert re.search(r"\blet\s+arriveTol\s*=", motion_src), (
        "motion.ts must declare the shared `arriveTol` state"
    )
    assert re.search(
        r"export function setArrivalTolerance\s*\(", motion_src
    ), "motion.ts must export setArrivalTolerance()"
    assert re.search(
        r"export function arrivalTolerance\s*\(", motion_src
    ), "motion.ts must export an arrivalTolerance() accessor"
    getter_body = _function_body("arrivalTolerance", motion_src)
    assert "arriveTol" in getter_body, (
        "arrivalTolerance() must return the shared arriveTol state"
    )


def test_arrive_tol_carries_no_unit_suffix():
    """.claude/rules/no-units-in-identifiers.md: the quantity's name
    says what it is, not the unit it happens to be measured in --
    `arriveTolCm` is exactly the violation that rule calls out by
    name. Renamed to `arriveTol` (unit in a trailing `// [cm]`
    comment) as part of this ticket, since the file was already being
    touched for the shared-state move."""
    for path, src in (
        (_MOTION_TS, _motion_ts_source()),
        (_WORLD_TS, _world_ts_source()),
    ):
        assert "arriveTolCm" not in src, (
            "%s still uses the unit-suffixed name arriveTolCm -- rename "
            "to arriveTol (unit goes in a trailing comment instead)" %
            path.name
        )


def test_world_ts_has_no_second_copy():
    """world.ts must not re-declare its own arriveTol/arriveTolCm state
    or its own setArrivalTolerance() -- a second, independent copy is
    exactly the defect this ticket fixes (one block's tolerance setting
    would silently stop affecting the other again)."""
    world_src = _world_ts_source()
    assert not re.search(r"\blet\s+arriveTol\s*=", world_src), (
        "world.ts must not declare its own arriveTol -- it must read "
        "motion.ts's shared value instead"
    )
    assert not re.search(
        r"export function setArrivalTolerance\s*\(", world_src
    ), (
        "world.ts must not export its own setArrivalTolerance() -- "
        "motion.ts's single exported function is the only one"
    )


def test_start_go_to_reads_shared_tolerance_not_a_hardcoded_literal():
    """motion.ts's startGoTo() must feed _goToR's `arrive` parameter
    from the shared arriveTol state, not a hardcoded literal (the old
    `const goalArrive = 1` -- 1 mm, regardless of setArrivalTolerance())."""
    motion_src = _motion_ts_source()
    body = _function_body("startGoTo", motion_src)
    m_assign = re.search(r"goalArrive\s*=\s*([^\n]*)", body)
    assert m_assign, "startGoTo() must assign a goalArrive value"
    assert "arriveTol" in m_assign.group(1), (
        "startGoTo() must derive goalArrive from the shared arriveTol "
        "state, not a hardcoded literal (the old `const goalArrive = "
        "1`, 1 mm regardless of setArrivalTolerance())"
    )
    calls = re.findall(r"_goToR\s*\(([^)]+)\)", body)
    assert calls, "startGoTo() must call _goToR(...) with arguments"
    assert any("goalArrive" in args for args in calls), (
        "startGoTo() must pass goalArrive (derived from arriveTol) as "
        "_goToR's arrive argument"
    )


def test_turn_first_is_a_const():
    """world.ts's turnFirst was a `let` nothing ever wrote -- grepped,
    no assignment anywhere else in the file. A `const` documents that
    it is a fixed threshold, not a runtime-tunable setting."""
    world_src = _world_ts_source()
    assert re.search(r"\bconst\s+turnFirst\s*=", world_src), (
        "world.ts's turnFirst must be declared `const`"
    )
    assert not re.search(r"\blet\s+turnFirst\s*=", world_src), (
        "world.ts must not declare turnFirst as a `let`"
    )
    # No reassignment anywhere in the file (only the declaration's own
    # `= 12.0` initializer should match `turnFirst =`).
    assignments = re.findall(r"\bturnFirst\s*=", world_src)
    assert len(assignments) == 1, (
        "turnFirst must be written exactly once (its own const "
        "initializer) -- found %d occurrences of `turnFirst =`" %
        len(assignments)
    )


def test_go_to_world_pre_check_reads_the_same_shared_value():
    """world.ts's goToWorld() own JS-level arrival pre-check must call
    motion.ts's arrivalTolerance() accessor -- the SAME shared
    arriveTol state startGoTo() feeds into _goToR -- not a second,
    independently-settable value, so one setArrivalTolerance() call
    visibly affects both go-to blocks."""
    world_src = _world_ts_source()
    body = _function_body("goToWorld", world_src)
    assert re.search(r"<=\s*arrivalTolerance\s*\(\s*\)", body), (
        "goToWorld()'s pre-check must compare against "
        "arrivalTolerance() (motion.ts), the same shared state "
        "startGoTo() feeds into _goToR"
    )
