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
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"


def _test_ts_source() -> str:
    return _TEST_TS.read_text(encoding="utf-8")


def _protocol_cpp_source() -> str:
    return _PROTOCOL_CPP.read_text(encoding="utf-8")


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


def test_abort_flag_declared_and_reset_by_every_tour():
    src = _test_ts_source()
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


def test_no_tour_emits_the_old_unconditional_tour_end():
    """The old bare `TOUR:end` (no reason suffix) must be gone -- every
    tour now emits TOUR:end:ok / TOUR:end:abort / TOUR:end:estop."""
    src = _test_ts_source()
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
