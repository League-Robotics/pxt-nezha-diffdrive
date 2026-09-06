"""tests/host/test_dispatched_job_motion_source_pin.py -- pins
`comms/protocol.cpp`'s own wiring for sprint 031 ticket 017,
clasi/sprints/031-drivetrain-tuning-and-gate-acceptance-on-tovez/
tickets/017-fix-motion-run-verbs-refused-by-their-own-dispatch-kjob-vs-
kblock-ownership-collision.md.

**What this is NOT.** Source-text pinning, following
`test_kblock_ownership_source_pin.py`'s own precedent -- `tests/host/`
cannot compile `comms/protocol.cpp` at all (it includes `pxt.h`,
directly and transitively). It cannot prove a real CODAL fiber calling
`Protocol::tryTakeMotionOwnership()` is actually recognized as the
dispatching fiber on real hardware, only that the source shape which
makes that possible is present. `test_motion_owner.py` is what proves
the underlying `diffDrive::tryTakeMotionOwnership()` decision logic is
correct, in isolation, for every (owner, isDispatchingFiber)
combination; `test_fiber_identity_gate.py` is what proves the fiber-
identity COMPARISON itself is correct, in isolation. This file proves
`Protocol::tryTakeMotionOwnership()` actually wires the two together
instead of falling back to the plain kBlock-only rule the ticket's own
defect came from.

**Why this matters, specifically.** The defect this ticket fixes was
NOT a bug in either pure decision function -- `tryTakeBlockOwnership()`
(motion_owner.h) and `shouldServiceHookRun()` (fiber_identity.h) were
both already correct in isolation, and both already had host tests
proving so, BEFORE this ticket. The bug was in the WIRING: nothing
combined "is this the dispatching fiber" with "does the caller already
hold kJob" at the one call site (`Protocol::tryTakeMotionOwnership()`,
née `tryTakeBlockOwnership()`) that needed both. A pure-function test
alone cannot catch a future regression that quietly reverts THIS file
back to an unconditional `diffDrive::tryTakeBlockOwnership(&motionOwner_)`
call -- that call is itself perfectly correct code, just wired wrong
for this call site's actual two kinds of caller. Hence this pin.

Run with::

    uv run pytest tests/host/test_dispatched_job_motion_source_pin.py
"""
import pathlib
import re

# tests/host/test_dispatched_job_motion_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROTOCOL_CPP = _REPO_ROOT / "src" / "comms" / "protocol.cpp"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    see test_bus_guard_source_pin.py's identical helper for the full
    rationale. Duplicated here rather than imported: each source-pin
    test file in this directory stays self-contained, the same
    precedent test_bus_guard_source_pin.py itself follows."""
    out_lines = []
    in_block = False
    for raw in text.splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                out_lines.append("")
                continue
        while "/*" in line:
            head, _, rest = line.partition("/*")
            if "*/" in rest:
                line = head + rest.split("*/", 1)[1]
            else:
                line = head
                in_block = True
                break
        line = line.split("//", 1)[0]
        out_lines.append(line)
    return "\n".join(out_lines)


def _function_body(source_text, signature_pattern, label):
    """Finds `signature_pattern` (a regex matching through the function's
    opening `{`) and returns the brace-matched body (not including the
    enclosing braces). Fails loudly, naming `label`, if the signature is
    not found -- distinguishing "renamed or removed" from "exists but
    lacks the call"."""
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in "
        f"{_PROTOCOL_CPP.relative_to(_REPO_ROOT)} -- has this function "
        f"been renamed or removed?"
    )
    depth = 0
    i = m.end() - 1  # the opening '{' itself
    while i < len(source_text):
        if source_text[i] == "{":
            depth += 1
        elif source_text[i] == "}":
            depth -= 1
            if depth == 0:
                return source_text[m.end():i]
        i += 1
    raise AssertionError(f"{label}: unbalanced braces scanning body")


_PROTOCOL_STRIPPED = _strip_comments(_PROTOCOL_CPP.read_text())

_TRY_TAKE_MOTION_OWNERSHIP_SIG = (
    r"\bbool\s+Protocol::tryTakeMotionOwnership\s*\(\s*\)\s*\{"
)


def _try_take_motion_ownership_body():
    return _function_body(
        _PROTOCOL_STRIPPED,
        _TRY_TAKE_MOTION_OWNERSHIP_SIG,
        "Protocol::tryTakeMotionOwnership",
    )


def test_computes_fiber_identity_before_taking_ownership():
    """The core of the fix: this function must compare the CURRENT
    fiber against protocolFiberId_ -- via currentFiberFn_(), the same
    reader serviceHookEntry() already uses -- rather than deciding
    purely from motionOwner_'s value, which is exactly the state-only
    check that let the regression through (a dispatched job's own call
    and a genuine block caller's call are indistinguishable by state
    alone; only fiber identity tells them apart)."""
    body = _try_take_motion_ownership_body()
    assert re.search(r"currentFiberFn_\s*\(\s*\)", body), (
        f"Protocol::tryTakeMotionOwnership(): no currentFiberFn_() call "
        f"-- it cannot tell a dispatched job's own call apart from a "
        f"genuine block caller's without reading which fiber this is:"
        f"\n{body}"
    )
    assert re.search(r"protocolFiberId_", body), (
        f"Protocol::tryTakeMotionOwnership(): no reference to "
        f"protocolFiberId_ -- currentFiberFn_()'s reading has nothing "
        f"to compare against:\n{body}"
    )


def test_delegates_to_the_shared_pure_decision_function():
    """The decision itself must be the ONE pure function
    core/motion_owner.h defines and test_motion_owner.py pins --
    diffDrive::tryTakeMotionOwnership(&motionOwner_, isDispatchingFiber)
    -- not a hand-rolled reimplementation here that could silently
    drift from what the host suite actually tested."""
    body = _try_take_motion_ownership_body()
    assert re.search(
        r"diffDrive::tryTakeMotionOwnership\s*\(\s*&\s*motionOwner_\s*,",
        body,
    ), (
        f"Protocol::tryTakeMotionOwnership(): does not call "
        f"diffDrive::tryTakeMotionOwnership(&motionOwner_, ...) -- the "
        f"shared, host-tested decision function from "
        f"core/motion_owner.h:\n{body}"
    )
    # And the OLD plain-kBlock-only call must be gone from this body --
    # calling both would mean the job-fiber bypass is dead code (the
    # block-only rule runs unconditionally right after it).
    assert not re.search(
        r"diffDrive::tryTakeBlockOwnership\s*\(\s*&\s*motionOwner_\s*\)",
        body,
    ), (
        f"Protocol::tryTakeMotionOwnership(): still calls the plain "
        f"diffDrive::tryTakeBlockOwnership(&motionOwner_) directly -- "
        f"this must go through diffDrive::tryTakeMotionOwnership() "
        f"instead, or the job-fiber bypass has no effect:\n{body}"
    )


def test_dispatch_job_still_sets_kjob_before_calling_the_handler():
    """The other half of the invariant this whole fix leans on:
    dispatchJob() must still claim motionOwner_ = kJob BEFORE calling
    runDispatch() (the TS handler) -- that is what makes
    `isDispatchingFiber && motionOwner_ == kJob` true for the handler's
    own motion call in the first place. If this ever stopped being
    true, the job-fiber bypass above would never fire and every
    dispatched RUN move would silently regress back to this ticket's
    own defect."""
    m = re.search(
        r"void Protocol::dispatchJob\(\)\s*\{(.*?)\n\}",
        _PROTOCOL_STRIPPED,
        re.DOTALL,
    )
    assert m, "Protocol::dispatchJob() was not found in protocol.cpp"
    body = m.group(1)
    set_kjob = re.search(r"motionOwner_\s*=\s*MotionOwner::kJob\s*;", body)
    run_dispatch_call = re.search(r"\brunDispatch\s*\(\s*\)\s*;", body)
    assert set_kjob, (
        f"Protocol::dispatchJob(): no 'motionOwner_ = MotionOwner::kJob;' "
        f"assignment found:\n{body}"
    )
    assert run_dispatch_call, (
        f"Protocol::dispatchJob(): no runDispatch() call found:\n{body}"
    )
    assert set_kjob.start() < run_dispatch_call.start(), (
        "Protocol::dispatchJob(): motionOwner_ is not set to kJob BEFORE "
        "runDispatch() -- the job-fiber bypass in "
        "Protocol::tryTakeMotionOwnership() depends on kJob already "
        "being set by the time the TS handler's own motion call arrives."
    )
