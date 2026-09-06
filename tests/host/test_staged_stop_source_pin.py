"""tests/host/test_staged_stop_source_pin.py -- pins the staged-stop
half of sprint 030 ticket 004 (glitch-armor-reject-raw-zero-and-staged-
cross-fiber-stop.md) across src/shims.cpp.

**What this fixes.** `deliverStopNow()` and the starvation watchdog used
to write the motor ports directly, from whichever fiber called them,
with no relationship to `busGuard` at all -- exactly the cross-fiber
I2C hazard `BusGuard` (sprint 030 ticket 001) exists to prevent for
every OTHER I2C-touching call site. A stop requested while some other
fiber is mid `kernel.step()` (holding the guard, possibly parked in its
own encoder settle sleep) could land its port write inside that
fiber's own settle window and destroy the in-flight encoder sample.
The fix stages the stop (`Rig::pendingStop_`) instead of writing across
the guard, delivered by the busy fiber itself, still inside its own
guarded window, right before it releases the guard -- the same
deferred-request shape `Rig::pendingOtosZero` already uses for `SET
rebase`'s OTOS write (test_bus_guard_source_pin.py pins that one).

**What this is NOT.** Source-text pinning, the same precedent
test_bus_guard_source_pin.py documents: `tests/host/` cannot compile
`shims.cpp` at all (it includes `pxt.h` transitively), so this proves
the source SHAPE that makes the fix possible is present, not that it
behaves correctly on real hardware under real concurrency.
`tests/host/test_bus_guard.py` is what proves `BusGuard::held()` itself
behaves correctly, in isolation.

Run with::

    uv run pytest tests/host/test_staged_stop_source_pin.py
"""
import pathlib
import re

# tests/host/test_staged_stop_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure --
    same technique test_bus_guard_source_pin.py uses, duplicated here
    (each source-pin file in this directory is self-contained, per
    precedent) rather than imported."""
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
    opening `{`) in `source_text` and returns the brace-matched body
    (NOT including the enclosing braces)."""
    m = re.search(signature_pattern, source_text)
    assert m, (
        f"{label}: no match for {signature_pattern!r} in "
        f"{_SHIMS_CPP.relative_to(_REPO_ROOT)} -- has this function been "
        f"renamed or removed?"
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


_SHIMS_STRIPPED = _strip_comments(_SHIMS_CPP.read_text())

_DELIVER_STOP_NOW_SIG = r"static\s+void\s+deliverStopNow\s*\(\s*Rig&\s*r\s*\)\s*\{"
_TICK_DRIVE_SIG = r"\bbool\s+tickDrive\s*\(\s*\)\s*\{"
_WATCHDOG_SIG = r"static\s+void\s+watchdogEntry\s*\(\s*void\*\s*context\s*\)\s*\{"

_DELIVER_STOP_NOW_BODY = _function_body(
    _SHIMS_STRIPPED, _DELIVER_STOP_NOW_SIG, "deliverStopNow"
)
_TICK_DRIVE_BODY = _function_body(_SHIMS_STRIPPED, _TICK_DRIVE_SIG, "tickDrive")
_WATCHDOG_BODY = _function_body(_SHIMS_STRIPPED, _WATCHDOG_SIG, "watchdogEntry")


def test_deliver_stop_now_stages_instead_of_writing_when_guard_is_held():
    """`deliverStopNow()` must check `busGuard.held()` and, when true,
    set `pendingStop_` and return WITHOUT writing the motor ports --
    the exact cross-fiber write this ticket closes."""
    assert re.search(r"busGuard\.held\s*\(\s*\)", _DELIVER_STOP_NOW_BODY), (
        f"deliverStopNow(): no busGuard.held() check:\n{_DELIVER_STOP_NOW_BODY}"
    )
    held_branch = re.search(
        r"if\s*\(\s*r\.busGuard\.held\s*\(\s*\)\s*\)\s*\{([^}]*)\}",
        _DELIVER_STOP_NOW_BODY,
    )
    assert held_branch, (
        "deliverStopNow(): could not isolate the busGuard.held() branch "
        f"body:\n{_DELIVER_STOP_NOW_BODY}"
    )
    branch_body = held_branch.group(1)
    assert "pendingStop_ = true" in branch_body, (
        f"deliverStopNow(): held()==true branch does not set pendingStop_:"
        f"\n{branch_body}"
    )
    assert "emergencyStop" not in branch_body, (
        "deliverStopNow(): held()==true branch still writes the motor "
        f"ports directly -- that is the exact race this ticket closes:"
        f"\n{branch_body}"
    )


def test_deliver_stop_now_still_writes_immediately_when_guard_is_free():
    """The common, uncontended path is unchanged: with the guard free,
    `deliverStopNow()` still writes both motor ports directly, with no
    added staging or latency."""
    assert re.search(r"\br\.left\.emergencyStop\s*\(\s*\)", _DELIVER_STOP_NOW_BODY), (
        f"deliverStopNow(): no unconditional r.left.emergencyStop() call:"
        f"\n{_DELIVER_STOP_NOW_BODY}"
    )
    assert re.search(r"\br\.right\.emergencyStop\s*\(\s*\)", _DELIVER_STOP_NOW_BODY), (
        f"deliverStopNow(): no unconditional r.right.emergencyStop() call:"
        f"\n{_DELIVER_STOP_NOW_BODY}"
    )


def test_deliver_stop_now_never_touches_the_estop_latch():
    """`deliverStopNow()` must stay a resumable soft stop: it must never
    call `kernel.estop()`, `kernel.emergencyStopMotors()`, or otherwise
    reach `estopLatch_` -- unchanged from before this ticket, and the
    staged path must not have introduced a new route to it."""
    assert not re.search(r"\bestop\b", _DELIVER_STOP_NOW_BODY, re.IGNORECASE), (
        f"deliverStopNow(): body now mentions estop in some form -- this "
        f"function must stay a resumable soft stop, never the latching "
        f"e-stop:\n{_DELIVER_STOP_NOW_BODY}"
    )


def test_tick_drive_delivers_pending_stop_before_releasing_the_guard():
    """The staged stop must be delivered by the SAME fiber that already
    holds busGuard, and it must happen BEFORE that fiber calls
    busGuard.release() -- delivering it after release would reopen the
    exact race this ticket closes (another fiber could acquire the
    guard and start its own I2C transaction in between)."""
    pending_pos = _TICK_DRIVE_BODY.find("pendingStop_")
    assert pending_pos != -1, (
        f"tickDrive(): no reference to pendingStop_ at all:\n{_TICK_DRIVE_BODY}"
    )
    release_pos = _TICK_DRIVE_BODY.find("busGuard.release()")
    assert release_pos != -1, "tickDrive(): no busGuard.release() at all"
    assert pending_pos < release_pos, (
        "tickDrive(): pendingStop_ is consumed AFTER busGuard.release() -- "
        "it must be delivered BEFORE release() while this fiber still "
        f"safely owns the guard:\n{_TICK_DRIVE_BODY}"
    )
    # The consuming branch must actually clear the flag and write both
    # ports, not just reference the name in a comment.
    branch = re.search(
        r"if\s*\(\s*r\.pendingStop_\s*\)\s*\{([^}]*)\}", _TICK_DRIVE_BODY
    )
    assert branch, (
        f"tickDrive(): no `if (r.pendingStop_) {{ ... }}` block found:"
        f"\n{_TICK_DRIVE_BODY}"
    )
    branch_body = branch.group(1)
    assert "pendingStop_ = false" in branch_body, (
        f"tickDrive(): pendingStop_ branch never clears the flag:\n{branch_body}"
    )
    assert "r.left.emergencyStop()" in branch_body, (
        f"tickDrive(): pendingStop_ branch does not stop the left port:"
        f"\n{branch_body}"
    )
    assert "r.right.emergencyStop()" in branch_body, (
        f"tickDrive(): pendingStop_ branch does not stop the right port:"
        f"\n{branch_body}"
    )


def test_watchdog_routes_through_deliver_stop_now_instead_of_writing_directly():
    """The starvation watchdog is the OTHER caller that used to write
    the motor ports directly, unconditionally -- it must now go through
    `deliverStopNow()` (which itself applies the busGuard.held() check)
    rather than calling `emergencyStop()` on the ports itself."""
    assert "deliverStopNow(r)" in _WATCHDOG_BODY, (
        f"watchdogEntry(): does not call deliverStopNow(r):\n{_WATCHDOG_BODY}"
    )
    assert "emergencyStop" not in _WATCHDOG_BODY, (
        "watchdogEntry(): still calls emergencyStop() on a port directly "
        f"-- it must go through deliverStopNow() instead:\n{_WATCHDOG_BODY}"
    )
