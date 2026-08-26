"""tests/host/test_run_abort_source_pin.py -- sprint 016 ticket 005
(closing run-tours-cannot-be-aborted.md): a text-level regression pin
for `test/test.ts`'s abort machinery, following
`test_block_toolbox_order.py`'s own precedent of regex-asserting on
`.ts` source text without compiling it (this repository's `tests/host/`
cannot compile or execute PXT/simulator code at all -- see
`tests/host/README.md`'s "What this does NOT cover yet").

**What this is NOT.** This is not a substitute for real verification.
It cannot prove `RUN:abort` actually stops a leg, that no further
`OCAL:` lines are emitted after an abort, or that the terminal-line
reason logic picks the right branch at runtime -- those all need either
a MakeCode/PXT build (ticket 007's build checkpoint) or a live robot
(bench/manual confirmation). All this proves is that the specific
source-text shapes ticket 005 introduced are actually present in
`test/test.ts` and that the OLD unconditional `TOUR:end` string is
gone -- cheap insurance against someone silently reverting or
refactoring the abort wiring away, nothing more.

Run with::

    uv run pytest tests/host/test_run_abort_source_pin.py
"""
import pathlib
import re

# tests/host/test_run_abort_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEST_TS = _REPO_ROOT / "test" / "test.ts"


def _source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def test_run_abort_handler_is_registered():
    src = _source()
    assert re.search(r'diffDrive\.onRun\(\s*"abort"\s*,', src), (
        "test/test.ts must register a diffDrive.onRun(\"abort\", ...) "
        "handler -- see this ticket's own description."
    )


def test_abort_flag_declared_and_reset_by_every_tour():
    src = _source()
    assert re.search(r'\blet\s+aborted\s*=\s*false\b', src), (
        "a module-level `let aborted = false` flag must exist"
    )
    # Each of the three tours resets it at the start, alongside `touring
    # = true` -- a crude but effective count: at least 4 occurrences of
    # `aborted = false` (the initial declaration plus one per tour).
    resets = re.findall(r'\baborted\s*=\s*false\b', src)
    assert len(resets) >= 4, (
        "expected the declaration plus a reset in each of tourRobot()/"
        "tourWheels()/tourWorld(), found: %r" % (resets,)
    )


def test_tick_to_completion_checks_aborted_and_stops_for_real():
    src = _source()
    match = re.search(
        r'function tickToCompletion\(\)\s*\{(.*?)\n\}', src, re.DOTALL)
    assert match, "tickToCompletion() not found in test/test.ts"
    body = match.group(1)
    assert "aborted" in body, (
        "tickToCompletion() -- the shared choke point every "
        "tickedMove()/tickedGoTo() leg goes through -- must check "
        "`aborted`"
    )
    assert "diffDrive.stopMove()" in body, (
        "an abort must call the REAL stop (diffDrive.stopMove()), not "
        "just exit the tick loop and leave the drivetrain commanded"
    )


def test_no_tour_emits_the_old_unconditional_tour_end():
    """The old bare `TOUR:end` (no reason suffix) must be gone -- every
    tour now emits TOUR:end:ok / TOUR:end:abort / TOUR:end:estop."""
    src = _source()
    assert 'emitLine("TOUR:end")' not in src, (
        "found the old unconditional TOUR:end -- every tour must emit "
        "a reason-suffixed TOUR:end:<ok|abort|estop> line instead"
    )
    # And the reason-aware form is actually present, at least once per
    # tour (tourRobot/tourWheels/tourWorld = 3).
    reasoned = re.findall(r'emitLine\("TOUR:end:"\s*\+\s*reason\)', src)
    assert len(reasoned) == 3, (
        "expected exactly 3 reason-aware TOUR:end emissions (one per "
        "tour), found: %d" % len(reasoned)
    )
