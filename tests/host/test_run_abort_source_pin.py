"""tests/host/test_run_abort_source_pin.py -- was written for sprint 016
ticket 005 (closing run-tours-cannot-be-aborted.md) to pin "an abort
handler exists" in `test/test.ts`. The executor inversion (sprint 028)
moves the interesting property: before that ticket, `RUN:abort` worked
only because the old MessageBus bridge forked a SECOND fiber for every
RUN command, so an abort landed concurrently with whatever tour it was
meant to stop -- "by accident," not by design. Once RUN dispatch and
wire motion collapse onto one fiber, that accident goes away, and abort
needs its OWN deliberate fast path that bypasses the RUN queue instead
-- a queued abort would sit behind the very job it is meant to stop.

So this file's pin moves from "an abort handler exists" (still checked
below, since the bypass has nothing to dispatch to without one) to "the
bypass is real": `Protocol::handleRun()` (protocol.cpp) recognizes
"abort"/"clearestop" by name and dispatches them immediately, without
going through `runQueue_.enqueue()` at all and without gating on
`motionOwner_`.

A later pass over `test.ts` itself found the wire-visible half of this
had rotted: `aborted` was reset only by the three original tours, so
any RUN:pivot/straight/face/cal/arc issued after a RUN:abort silently
truncated to one tick and reported a normal end, and five newer tours
plus RUN:cal applied no shaping profile and emitted no reasoned
terminal line at all. The fix collapses every job's own
reset/profile/terminal-line handling into one `beginJob()`/`endJob()`
pair; the tests below pin THAT single choke point rather than counting
per-handler duplicates the way this file used to.

**What this is NOT.** Source-text pinning, following
`test_block_toolbox_order.py`'s own precedent of regex-asserting on
source text without compiling it -- `tests/host/` cannot compile
`protocol.cpp` (it includes `pxt.h` transitively) or execute PXT/
simulator code at all (see `tests/host/README.md`'s "What this does NOT
cover yet"). It cannot prove an abort sent mid-tour on real hardware
actually lands before the tour's own next tick, only that the source
shape which makes that possible is present. That needs a robot.

Run with::

    uv run pytest tests/host/test_run_abort_source_pin.py
"""
import pathlib
import re

# tests/host/test_run_abort_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TEST_TS = _REPO_ROOT / "test" / "test.ts"
_WORLD_TS = _REPO_ROOT / "src" / "blocks" / "world.ts"
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"

# Every motion-issuing plain function that must run through
# beginJob()/endJob() -- the tour functions and the two ("straight",
# "cal") whose onRun() handler is a one-line call into one of these,
# so the job lifecycle lives in the function, not the handler body.
_JOB_FUNCTIONS = (
    "tourRobot", "tourWheels", "tourWorld", "straightRun", "leverCal",
    "squareTour", "infinityTour", "snakeTour", "diamondTour", "circleTour",
)
# The remaining motion-issuing onRun() verbs, where beginJob()/endJob()
# live directly in the handler body instead of a named function.
_JOB_ONRUN_VERBS = ("goto", "face", "pivot", "arc")


def _test_ts_source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def _world_ts_source() -> str:
    return _WORLD_TS.read_text(encoding="utf-8")


def _protocol_cpp_source() -> str:
    return _PROTOCOL_CPP.read_text(encoding="utf-8")


def _shims_cpp_source() -> str:
    return _SHIMS_CPP.read_text(encoding="utf-8")


def _find_balanced_close(text: str, open_brace_idx: int) -> int:
    """Index just past the '}' matching the '{' at open_brace_idx."""
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


def _function_body(name: str, src: str = None) -> str:
    """Body of `function <name>(...) {...}` in test.ts, brace-balanced
    (a naive non-greedy regex breaks on any handler with a nested
    `{...}` block, which every for-loop-bearing one here has)."""
    src = _test_ts_source() if src is None else src
    m = re.search(r"function\s+%s\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{" %
                  re.escape(name), src)
    assert m, "function %s() not found" % name
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.end():close_idx - 1]


def _onrun_body(verb: str) -> str:
    """Body of `diffDrive.onRun("<verb>", function (...) {...})`,
    brace-balanced -- same reasoning as _function_body()."""
    src = _test_ts_source()
    m = re.search(
        r'diffDrive\.onRun\(\s*"%s"\s*,\s*function\s*\([^)]*\)\s*\{' %
        re.escape(verb), src)
    assert m, 'diffDrive.onRun("%s", ...) not found' % verb
    open_idx = m.end() - 1
    close_idx = _find_balanced_close(src, open_idx)
    return src[m.end():close_idx - 1]


# ---------------------------------------------------------------------------
# test.ts: the abort machinery a bypass needs something to dispatch to.
# ---------------------------------------------------------------------------


def test_run_abort_handler_is_registered():
    src = _test_ts_source()
    assert re.search(r'diffDrive\.onRun\(\s*"abort"\s*,', src), (
        "test/test.ts must register a diffDrive.onRun(\"abort\", ...) "
        "handler -- the queue-bypass path (protocol.cpp) has nothing to "
        "dispatch to without one."
    )


def test_abort_handler_calls_stop_move():
    """BT-11: RUN:abort must not just set the flag -- it must call the
    REAL stop, so it can interrupt a move in flight anywhere, including
    inside goToWorld()'s own tick loop in world.ts, which has no
    visibility into `aborted` at all."""
    body = _onrun_body("abort")
    assert re.search(r"\baborted\s*=\s*true\b", body), (
        "RUN:abort must still set aborted = true"
    )
    assert "diffDrive.stopMove()" in body, (
        "RUN:abort must call diffDrive.stopMove() -- without it, an "
        "abort sent during a goToWorld leg can only prevent the NEXT "
        "leg from starting, not stop the one in flight"
    )


def test_begin_job_and_end_job_exist():
    src = _test_ts_source()
    assert re.search(r"function\s+beginJob\s*\(", src), (
        "test.ts must define a single beginJob() job-entry function"
    )
    assert re.search(r"function\s+endJob\s*\(", src), (
        "test.ts must define a single endJob() job-exit function"
    )


def test_aborted_is_reset_only_inside_begin_job():
    """The single choke point every job resets `aborted` through now.
    Before this ticket, only the three original tours reset it, so any
    RUN:pivot/straight/face/cal/arc issued after a RUN:abort silently
    truncated to one tick. If this count grows above 2 (the declaration
    plus beginJob()'s own reset), some handler is hand-rolling its own
    reset again instead of going through beginJob()."""
    body = _function_body("beginJob")
    assert re.search(r"\baborted\s*=\s*false\b", body), (
        "beginJob() must reset `aborted = false`"
    )
    src = _test_ts_source()
    resets = re.findall(r"\baborted\s*=\s*false\b", src)
    assert len(resets) == 2, (
        "expected exactly 2 occurrences of `aborted = false` (the "
        "declaration and beginJob()'s own reset), found: %r" % (resets,)
    )


def test_every_motion_job_calls_begin_job_and_end_job():
    """Every motion-issuing job -- not just the three original tours --
    must go through the shared pair, with no handler left hand-rolling
    any subset of reset/profile/terminal-line on its own."""
    for fn in _JOB_FUNCTIONS:
        body = _function_body(fn)
        assert "beginJob(" in body, "%s() does not call beginJob()" % fn
        assert "endJob(" in body, "%s() does not call endJob()" % fn
    for verb in _JOB_ONRUN_VERBS:
        body = _onrun_body(verb)
        assert "beginJob(" in body, (
            'RUN:%s handler does not call beginJob()' % verb
        )
        assert "endJob(" in body, (
            'RUN:%s handler does not call endJob()' % verb
        )


def test_tick_to_completion_checks_aborted_and_stops_for_real():
    src = _test_ts_source()
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


def test_no_bare_unreasoned_terminal_lines_remain():
    """The old ad hoc terminal lines (no reason suffix) must be gone --
    every job's terminal line now goes through endJob(), which always
    appends a reason."""
    src = _test_ts_source()
    for bare in ('emitLine("TOUR:end")', 'emitLine("PIVOT:end")',
                 'emitLine("ARC:end")', 'emitLine("FACE:end")',
                 'emitLine("GOTO:end")'):
        assert bare not in src, (
            "found the old unreasoned %s -- every terminal line must "
            "now go through endJob()" % bare
        )


def test_end_job_emits_gap_then_reasoned_terminal_line():
    body = _function_body("endJob")
    gap_match = re.search(r'emitLine\(\s*"GAP:"\s*\+\s*maxGap\s*\)', body)
    end_match = re.search(r'":end:"\s*\+\s*reason', body)
    assert gap_match, "endJob() must emit the GAP: line"
    assert end_match, (
        "endJob() must emit a terminal line containing ':end:' followed "
        "by the reason argument"
    )
    assert gap_match.start() < end_match.start(), (
        "GAP: must be emitted BEFORE the terminal <VERB>:end:<reason> "
        "line, matching every job's original ordering"
    )


def test_job_reason_priority_matches_abort_over_estop_over_ok():
    """Reason priority: abort (operator intent) beats a coincident
    e-stop, which beats a clean finish -- the same order tourRobot's
    original comment documented."""
    body = _function_body("jobReason")
    assert re.search(
        r'aborted\s*\?\s*"abort"\s*:\s*\('
        r'diffDrive\.probe\(1\)\s*!=\s*0\s*\?\s*"estop"\s*:\s*"ok"\s*\)',
        body,
    ), (
        "jobReason() must return \"abort\" if aborted, else \"estop\" if "
        "diffDrive.probe(1) is nonzero, else \"ok\" -- found: %r" % body
    )


# ---------------------------------------------------------------------------
# Open Question 1 (sprint.md Architecture): does stopMove() ever refuse
# to stop a move it doesn't "own"? Confirmed by source, not assumption.
# ---------------------------------------------------------------------------


def test_end_move_stops_unconditionally_with_no_ownership_gate():
    """`diffDrive.stopMove()`'s native body is shims.cpp's endMove().
    For RUN:abort to interrupt a goToWorld leg (BT-11), this must stop
    whatever tick loop is currently active with NO motionOwner_ check
    -- unlike the queued dispatchJob() path, which correctly refuses to
    START a new job while something else owns the drivetrain (see
    test_dispatch_job_refuses_while_something_already_owns_motion
    below, the contrast case)."""
    text = _shims_cpp_source()
    m = re.search(r"void endMove\(\)\s*\{(.*?)\n\}", text, re.DOTALL)
    assert m, "endMove() not found in shims.cpp"
    body = m.group(1)
    assert "motionOwner_" not in body, (
        "endMove() now checks motionOwner_ -- stopMove() would no "
        "longer be able to interrupt a move it doesn't 'own', silently "
        "breaking RUN:abort during a goToWorld leg"
    )
    assert "engine.endMove()" in body, (
        "endMove() no longer calls the move engine's own endMove() -- "
        "this is what actually ends the tick loop's isDriving() state"
    )


def test_world_ts_tick_loops_have_no_local_abort_flag():
    """world.ts's tickedMove()/tickedGoTo() (goToWorld()'s own tick
    runner) must rely ENTIRELY on `_tickDrive()` going false -- i.e. on
    stopMove() reaching in from outside -- to end early. They have no
    way to see test.ts's `aborted` at all; if they ever gained their
    own abort check it would mean someone tried to plumb the flag
    across files instead of trusting the universal stopMove() path."""
    src = _world_ts_source()
    for fn in ("tickedMove", "tickedGoTo"):
        body = _function_body(fn, src=src)
        assert "_tickDrive" in body, "%s() must tick via _tickDrive()" % fn
        assert "aborted" not in body, (
            "%s() references `aborted` -- it has no way to see test.ts's "
            "module-level flag; it must rely on stopMove() alone" % fn
        )


# ---------------------------------------------------------------------------
# protocol.cpp: abort/clearestop bypass the queue -- the property this
# ticket actually moves the pin onto.
# ---------------------------------------------------------------------------


def _handle_run_body():
    text = _protocol_cpp_source()
    match = re.search(
        r"void Protocol::handleRun\([^)]*\)\s*\{(.*?)\n\}", text, re.DOTALL
    )
    assert match, "Protocol::handleRun() was not found in protocol.cpp"
    return match.group(1)


def test_handle_run_recognizes_abort_and_clearestop_by_name():
    """A bypass has to name what it bypasses for. Both names test.ts
    binds to non-blocking handlers (clearing a flag / clearing a latch)
    must be recognized somewhere in protocol.cpp's own RUN-bridge
    machinery, not just in test.ts."""
    text = _protocol_cpp_source()
    assert re.search(r'"abort"', text), (
        "protocol.cpp no longer names \"abort\" anywhere -- the bypass "
        "this file pins has been removed or renamed."
    )
    assert re.search(r'"clearestop"', text), (
        "protocol.cpp no longer names \"clearestop\" anywhere -- the "
        "bypass this file pins has been removed or renamed."
    )


def test_handle_run_dispatches_the_bypass_names_before_enqueueing():
    """The bypass must be checked, and act, BEFORE handleRun() ever
    reaches runQueue_.enqueue() -- if the bypass ran after an enqueue
    attempt (or not at all), "abort"/"clearestop" would sit in the queue
    behind whatever job is already running, exactly the queue-delay this
    ticket exists to remove."""
    body = _handle_run_body()
    bypass_call = re.search(r"invokeRunDispatch\(", body)
    enqueue_call = re.search(r"runQueue_\.enqueue\(", body)
    assert bypass_call, (
        "Protocol::handleRun() no longer calls invokeRunDispatch() -- "
        "the direct-dispatch bypass this file pins is gone."
    )
    assert enqueue_call, (
        "Protocol::handleRun() no longer calls runQueue_.enqueue() at "
        "all -- expected the bypass names to be the ONLY ones that skip "
        "the queue, not for the queue itself to have been removed."
    )
    assert bypass_call.start() < enqueue_call.start(), (
        "invokeRunDispatch() (the bypass) must be reached, and return, "
        "BEFORE runQueue_.enqueue() in handleRun()'s own source order -- "
        "found it AFTER the enqueue call instead, which means an abort "
        "would be queued like any other command rather than bypassing "
        "it."
    )


def test_bypass_dispatch_does_not_gate_on_motion_owner():
    """The bypass call itself (handleRun() invoking invokeRunDispatch()
    directly) must not be wrapped in any motionOwner_ check -- unlike
    dispatchJob() (which refuses to start a new job while something else
    already owns the drivetrain), abort/clearestop must land regardless
    of what motionOwner_ currently is. This checks the one line
    handleRun() uses to reach the bypass, not the whole function body,
    so an unrelated motionOwner_ check elsewhere in the file can't
    produce a false failure here."""
    body = _handle_run_body()
    match = re.search(r"^.*invokeRunDispatch\([^\n]*$", body, re.MULTILINE)
    assert match, "invokeRunDispatch() call site not found in handleRun()"
    assert "motionOwner_" not in match.group(0), (
        "handleRun()'s own invokeRunDispatch() call site mentions "
        "motionOwner_ -- the bypass must be UNGATED; gating it on "
        "motionOwner_ would reintroduce the queue-delay this ticket "
        "removes."
    )


def test_dispatch_job_refuses_while_something_already_owns_motion():
    """The CONTRAST case: dispatchJob() (a queued, non-bypass job) is
    correctly gated -- it must not start a second job (or start one
    while wire motion is live) by checking motionOwner_ before doing
    anything else."""
    text = _protocol_cpp_source()
    match = re.search(
        r"void Protocol::dispatchJob\(\)\s*\{(.*?)\n\}", text, re.DOTALL
    )
    assert match, "Protocol::dispatchJob() was not found in protocol.cpp"
    body = match.group(1)
    assert "motionOwner_" in body, (
        "Protocol::dispatchJob() no longer checks motionOwner_ -- "
        "without that gate a queued job could start while a wire motion "
        "or another job is already running."
    )
