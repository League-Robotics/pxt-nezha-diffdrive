"""tests/host/test_bus_guard_source_pin.py -- pins BusGuard coverage
across `src/shims.cpp` and `src/platform/otos_port.cpp` (sprint 030
ticket 001, clasi/sprints/030-bus-discipline-and-fiber-safety/issues/
enforce-the-one-fiber-i2c-invariant.md).

**What this is NOT.** Source-text pinning, following
`test_run_abort_source_pin.py`'s / `test_vfp_guard_source_pin.py`'s own
precedent of regex-asserting on source text without compiling it --
`tests/host/` cannot compile `shims.cpp` or `otos_port.cpp` at all
(both include `pxt.h`, directly or transitively). It cannot prove a
guarded call site actually excludes a concurrent caller on real
hardware, only that the source shape which makes that possible is
present. `tests/host/test_bus_guard.py` is what proves BusGuard's own
acquire/release logic behaves correctly, in isolation; this file proves
the six shims.cpp entry points and tickDrive() actually USE it.

**Why this file also inventories otos_port.cpp's I2C surface.** The
guard itself cannot live inside OtosPort: `otos_port.h` has no
`DiffDrive::Sleeper` of its own to spin on (that lives on `Rig`, in
shims.cpp), so every guarded call happens at the shims.cpp call site,
around the OtosPort method invocation -- not inside OtosPort's own
methods. That means "does this OtosPort method touch I2C" and "is
every CALLER of it guarded" are two separate questions this file
answers separately:

1. `_i2c_touching_otos_port_methods()` walks otos_port.cpp's own call
   graph (i2cWrite/i2cRead -> writeReg8/readReg8/writeXYH -> writePoseMm
   -> begin/read/setOffset/setPose/resetTracking/calibrateImu/
   imuCalibrationSamplesRemaining, plus zeroPose's inline delegation to
   setPose in otos_port.h) to produce the CLOSED set of method names
   that reach `uBit.i2c`. If a future edit adds I2C to a method not in
   this hardcoded set, `test_no_new_i2c_touching_methods_appear_unnoticed`
   fails -- forcing whoever adds it to update this test (and, more
   importantly, to ask whether the new path needs guarding).
2. The six per-function body tests confirm shims.cpp's six named entry
   points (`otosBegin`, `otosRead`, `otosZero`, `otosCalibrate`,
   `otosSetOffset`, `seedPose`) each bracket their OtosPort call with
   `busGuard.acquire()`/`release()`.

**`otosGet()` case 8 was a known gap; it is now closed.** This file's
own call-graph walk found that `otosGet()`'s case 8 (`shims.cpp`) reads
`o.imuCalibrationSamplesRemaining()`, an I2C-touching method
(`readReg8`) -- but `otosGet()` was not one of the six entry points the
originating issue named, and was initially shipped unguarded on
scope-discipline grounds. The ticket was reopened to close it instead:
case 8 now brackets the call in `busGuard.acquire()`/`release()` the
same as the six named entry points, and
`test_otosget_case_8_acquires_and_releases_bus_guard` below asserts
that positively (replacing the earlier known-gap pin).

**Remaining known, deliberately out-of-scope gap.** `resetTracking()`
is also I2C-touching (per the call-graph walk) but is never called from
`shims.cpp` at all (dead from the shim layer's perspective), so it is
not a live hole -- only a dead method that would need a guarded entry
point the day something starts calling it.
`test_known_gap_reset_tracking_is_unguarded_but_also_unreachable` below
pins that CURRENT state instead of hiding it.

Run with::

    uv run pytest tests/host/test_bus_guard_source_pin.py
"""
import pathlib
import re

# tests/host/test_bus_guard_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"
_OTOS_PORT_H = _REPO_ROOT / "src" / "platform" / "otos_port.h"
_OTOS_PORT_CPP = _REPO_ROOT / "src" / "platform" / "otos_port.cpp"


def _strip_comments(text):
    """Strips `//` and `/* */` comments, preserving line structure (blank
    lines replace removed content) so later regex offsets still line up
    with something readable on failure. Mirrors
    test_vfp_guard_source_pin.py's own `_code_lines()` stripping, but
    returns one flat string (not per-line tuples) since this file needs
    to brace-match a function body across line boundaries.
    """
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
    (NOT including the enclosing braces). Fails loudly, naming `label`,
    if the signature is not found at all -- distinguishing "renamed or
    removed" from "exists but lacks the guard"."""
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

# The six OTOS shim entry points this ticket's issue names
# (enforce-the-one-fiber-i2c-invariant.md's own Remedy list), plus
# tickDrive() itself (the ORIGINAL stepBusy holder, now BusGuard's other
# caller). {label: (signature regex, whether call is expected inline)}
_GUARDED_FUNCTIONS = {
    "otosBegin": r"\bint\s+otosBegin\s*\(\s*\)\s*\{",
    "otosRead": r"\bbool\s+otosRead\s*\(\s*\)\s*\{",
    "otosZero": r"\bvoid\s+otosZero\s*\(\s*\)\s*\{",
    "otosCalibrate": r"\bvoid\s+otosCalibrate\s*\(\s*int\s+samples\s*\)\s*\{",
    "otosSetOffset": (
        r"\bvoid\s+otosSetOffset\s*\(\s*int\s+x,\s*int\s+y,\s*int\s+yaw\s*\)"
        r"\s*\{"
    ),
    "seedPose": (
        r"\bvoid\s+seedPose\s*\(\s*int\s+x,\s*int\s+y,\s*int\s+heading\s*\)"
        r"\s*\{"
    ),
    "tickDrive": r"\bbool\s+tickDrive\s*\(\s*\)\s*\{",
}


def _test_ids():
    return sorted(_GUARDED_FUNCTIONS.keys())


import pytest  # noqa: E402  (after the module-level constants above)


@pytest.mark.parametrize("name", _test_ids())
def test_entry_point_acquires_and_releases_bus_guard(name):
    """Each of these seven functions' bodies must call BOTH
    `busGuard.acquire(...)` and `busGuard.release()` -- the three-line
    pattern (acquire, do the I2C call, release) the ticket's own Remedy
    specifies. A function calling only one of the two would leave the
    guard permanently held or never actually taken."""
    body = _function_body(_SHIMS_STRIPPED, _GUARDED_FUNCTIONS[name], name)
    assert re.search(r"busGuard\.acquire\s*\(", body), (
        f"{name}(): body has no busGuard.acquire(...) call:\n{body}"
    )
    assert re.search(r"busGuard\.release\s*\(\s*\)", body), (
        f"{name}(): body has no busGuard.release() call:\n{body}"
    )


def test_stepbusy_flag_is_gone_from_shims_cpp():
    """The pre-ticket `Rig::stepBusy` bare bool must not reappear as a
    live identifier -- BusGuard replaces it entirely (comments that
    mention the old name for historical context are fine; this checks
    the COMMENT-STRIPPED text)."""
    assert "stepBusy" not in _SHIMS_STRIPPED, (
        "stepBusy still appears as live code in shims.cpp -- it should "
        "have been fully replaced by Rig::busGuard (BusGuard)."
    )


def test_pending_otos_zero_is_consumed_after_release_inside_tick_drive():
    """SET rebase's OTOS write must be deferred (a `pendingOtosZero`
    flag) and consumed INSIDE tickDrive() -- and specifically AFTER
    r.busGuard.release() from tickDrive()'s own kernel.step() span, so
    the deferred write gets its own separate acquire/release pair
    rather than piggy-backing on the step's still-held guard."""
    body = _function_body(
        _SHIMS_STRIPPED, _GUARDED_FUNCTIONS["tickDrive"], "tickDrive"
    )
    release_pos = body.find("busGuard.release()")
    assert release_pos != -1, "tickDrive(): no busGuard.release() at all"
    pending_pos = body.find("pendingOtosZero", release_pos)
    assert pending_pos != -1, (
        "tickDrive(): pendingOtosZero is not consumed AFTER the first "
        "busGuard.release() -- it must run after the kernel.step() span "
        "releases the guard, not before or during it."
    )


def test_set_rebase_defers_the_otos_write_instead_of_calling_it_synchronously():
    """setKernelValue()'s case 32 body must SET the pendingOtosZero flag,
    not call otosRef().setPose(...) directly -- the synchronous call is
    exactly the hole this ticket closes."""
    m = re.search(r"case 32:\s*\{?", _SHIMS_STRIPPED)
    assert m, "case 32 (SET rebase) not found in shims.cpp"
    # The case body runs from here to the next `case ` or `default:` at
    # the same switch level (rebase has no nested braces of its own, so
    # a plain scan to the next sibling label is enough).
    tail = _SHIMS_STRIPPED[m.end():]
    next_label = re.search(r"\n\s*(case \d+:|default:)", tail)
    case_body = tail[: next_label.start()] if next_label else tail
    assert "pendingOtosZero = true" in case_body, (
        f"case 32 (SET rebase) does not set pendingOtosZero:\n{case_body}"
    )
    assert "otosRef().setPose" not in case_body, (
        "case 32 (SET rebase) still calls otosRef().setPose(...) "
        f"synchronously instead of deferring it:\n{case_body}"
    )


# ---- otos_port.cpp: the closed inventory of I2C-touching methods -------

_OTOS_PORT_CPP_STRIPPED = _strip_comments(_OTOS_PORT_CPP.read_text())
_OTOS_PORT_H_STRIPPED = _strip_comments(_OTOS_PORT_H.read_text())

# Private helpers that call i2cWrite()/i2cRead() DIRECTLY (the base of
# the call graph) -- confirmed by reading otos_port.cpp (2026-09-04,
# this ticket's own review, not a hardware measurement: this is source
# reading, not MEASURED behavior).
_DIRECT_I2C_HELPERS = {"writeReg8", "readReg8", "writeXYH"}


def test_direct_i2c_helpers_are_still_exactly_this_set():
    """Pins the base of the call graph the rest of this file's
    inventory relies on: exactly these three OtosPort methods call
    i2cWrite()/i2cRead() directly in otos_port.cpp. If a new direct
    caller appears (or one of these stops being one), the derived
    inventory below is no longer trustworthy without a human looking
    again."""
    found = set()
    for m in re.finditer(
        r"bool\s+OtosPort::(\w+)\s*\([^)]*\)\s*\{", _OTOS_PORT_CPP_STRIPPED
    ):
        name = m.group(1)
        body = _function_body(
            _OTOS_PORT_CPP_STRIPPED,
            re.escape(m.group(0)),
            f"OtosPort::{name}",
        )
        if re.search(r"\bi2c(Write|Read)\s*\(", body):
            found.add(name)
    # `read()` also matches this pattern (`bool OtosPort::read()`,
    # `[^)]*` covers the empty-parameter case) and DOES call i2cWrite/
    # i2cRead directly -- but it is the public entry point itself, not
    # a low-level helper other methods build on, so it is excluded from
    # this specific set (it is still covered by the broader transitive
    # inventory in test_no_new_i2c_touching_methods_appear_unnoticed
    # below, which includes it explicitly).
    found.discard("read")
    assert found == _DIRECT_I2C_HELPERS, (
        f"direct i2cWrite/i2cRead callers changed: found {sorted(found)}, "
        f"expected {sorted(_DIRECT_I2C_HELPERS)}. Update "
        f"_DIRECT_I2C_HELPERS and re-derive the transitive I2C-touching "
        f"method set below."
    )


# The full transitive closure, re-derived by hand from
# _DIRECT_I2C_HELPERS (2026-09-04 source reading, not a generic
# algorithm -- otos_port.cpp is small and stable enough that a hand
# derivation, re-checked by the test above every run, is clearer than a
# tiny call-graph walker would be):
#   writeReg8, readReg8, writeXYH  -- direct (confirmed above)
#   writePoseMm                    -- calls writeXYH
#   begin                          -- calls readReg8, writeReg8, writePoseMm
#   read                           -- calls i2cWrite/i2cRead directly
#   setOffset                      -- calls writePoseMm (if initialized_)
#   setPose                        -- calls writePoseMm
#   resetTracking                  -- calls writeReg8
#   calibrateImu                   -- calls writeReg8
#   imuCalibrationSamplesRemaining -- calls readReg8
#   zeroPose (otos_port.h, inline) -- delegates to setPose(0,0,0)
_I2C_TOUCHING_METHODS = {
    "begin",
    "read",
    "setOffset",
    "setPose",
    "resetTracking",
    "calibrateImu",
    "imuCalibrationSamplesRemaining",
    "zeroPose",
}

# shims.cpp's six guarded entry points, and the OtosPort method each one
# calls (zeroPose -> setPose is the one indirection).
_GUARDED_ENTRY_CALLS_METHOD = {
    "otosBegin": "begin",
    "otosRead": "read",
    "otosZero": "zeroPose",
    "otosCalibrate": "calibrateImu",
    "otosSetOffset": "setOffset",
    "seedPose": "setPose",
}


def test_no_new_i2c_touching_methods_appear_unnoticed():
    """Walks otos_port.cpp (plus otos_port.h's inline zeroPose()) for
    every method that reaches an I2C-touching helper (transitively) and
    confirms the set matches the hand-derived inventory above exactly.
    A new method added here without updating this test is a signal that
    someone needs to ask whether shims.cpp has a guarded entry point for
    it."""
    i2c_helpers_and_derivatives = set(_DIRECT_I2C_HELPERS) | {"writePoseMm"}
    found = set()
    for m in re.finditer(
        r"\b(?:bool|void|uint8_t)\s+OtosPort::(\w+)\s*\([^)]*\)\s*\{",
        _OTOS_PORT_CPP_STRIPPED,
    ):
        name = m.group(1)
        body = _function_body(
            _OTOS_PORT_CPP_STRIPPED,
            re.escape(m.group(0)),
            f"OtosPort::{name}",
        )
        calls_i2c_directly = re.search(r"\bi2c(Write|Read)\s*\(", body)
        calls_a_helper = any(
            re.search(rf"\b{helper}\s*\(", body)
            for helper in i2c_helpers_and_derivatives
        )
        if calls_i2c_directly or calls_a_helper:
            found.add(name)
    # The low-level helpers themselves (writeReg8/readReg8/writeXYH,
    # confirmed above, plus writePoseMm which calls writeXYH) match this
    # same scan -- they call i2cWrite/i2cRead or each other. They are
    # plumbing, not the public-facing "methods" this inventory is about
    # (no shims.cpp caller ever reaches them directly), so they are
    # excluded from `found` here rather than added to
    # _I2C_TOUCHING_METHODS.
    found -= _DIRECT_I2C_HELPERS | {"writePoseMm"}
    # zeroPose() is inline in otos_port.h, not otos_port.cpp -- add it
    # explicitly since it is a real I2C-touching entry (delegates to
    # setPose(0,0,0)) that the .cpp-only scan above cannot see.
    zero_pose_match = re.search(
        r"void\s+zeroPose\s*\(\s*\)\s*\{[^}]*\}", _OTOS_PORT_H_STRIPPED
    )
    assert zero_pose_match, (
        "OtosPort::zeroPose() not found inline in otos_port.h -- has it "
        "moved to otos_port.cpp? If so, the scan above should pick it "
        "up automatically and this special case can be removed."
    )
    assert "setPose" in zero_pose_match.group(0), (
        "zeroPose() no longer delegates to setPose() -- re-derive "
        "whether it still touches I2C."
    )
    found.add("zeroPose")

    assert found == _I2C_TOUCHING_METHODS, (
        f"I2C-touching OtosPort methods changed: found {sorted(found)}, "
        f"expected {sorted(_I2C_TOUCHING_METHODS)}. If a new method was "
        f"added, decide whether shims.cpp needs a NEW guarded entry "
        f"point for it before updating this expected set."
    )


@pytest.mark.parametrize(
    "entry_name,method_name", sorted(_GUARDED_ENTRY_CALLS_METHOD.items())
)
def test_guarded_entry_calls_an_i2c_touching_method(entry_name, method_name):
    """Cross-check: each of the six guarded shims.cpp entry points
    (already proven to acquire/release BusGuard, above) actually calls
    the OtosPort method this file's own inventory says touches I2C --
    guarding a call that does not exist, or that touches no I2C, would
    make the earlier acquire/release assertions vacuous."""
    assert method_name in _I2C_TOUCHING_METHODS, (
        f"{method_name} (called by {entry_name}) is not in this file's "
        f"own I2C-touching inventory -- inventory or mapping is stale."
    )


def test_otosget_case_8_acquires_and_releases_bus_guard():
    """otosGet()'s case 8 is the only case in this switch that touches
    I2C -- it calls o.imuCalibrationSamplesRemaining(), which this
    file's own inventory (above) confirms reaches readReg8(). Every
    other case reads a cached field set by the last read()/begin()
    (x/y/heading/vx/vy/omega/productId/connected), so only case 8 needs
    a guard. This replaces the earlier known-gap pin
    (test_known_gap_otosget_case_8_reads_an_i2c_touching_method_unguarded)
    now that the gap is closed: case 8 brackets its I2C call in
    busGuard.acquire()/release() exactly like the six named entry points
    above, isolated to case 8's own braced block so the other seven
    cases (which must NOT take the guard -- they touch no I2C) are not
    silently satisfying this assertion instead."""
    fn_match = re.search(
        r"\bint\s+otosGet\s*\(\s*int\s+what\s*\)\s*\{", _SHIMS_STRIPPED
    )
    assert fn_match, "otosGet() not found in shims.cpp -- has it been renamed?"
    fn_body = _function_body(_SHIMS_STRIPPED, re.escape(fn_match.group(0)), "otosGet")

    case_match = re.search(r"case 8:\s*\{", fn_body)
    assert case_match, (
        "otosGet(): case 8 no longer opens its own braced block -- has "
        "the guard been removed or the case body reshaped? (a bare "
        "`case 8: return ...;` with no braces would mean the gap is "
        "back)"
    )
    case_body = _function_body(
        fn_body, re.escape(case_match.group(0)), "otosGet case 8"
    )
    assert "imuCalibrationSamplesRemaining" in case_body, (
        "otosGet(): case 8 no longer calls imuCalibrationSamplesRemaining() "
        f"-- has it moved to a different case?:\n{case_body}"
    )
    assert re.search(r"busGuard\.acquire\s*\(", case_body), (
        f"otosGet(): case 8 has no busGuard.acquire(...) call:\n{case_body}"
    )
    assert re.search(r"busGuard\.release\s*\(\s*\)", case_body), (
        f"otosGet(): case 8 has no busGuard.release() call:\n{case_body}"
    )


# ---- known, deliberately out-of-scope gap (pinned, not hidden) --------

def test_known_gap_reset_tracking_is_unguarded_but_also_unreachable():
    """PINS the OTHER known gap: OtosPort::resetTracking() touches I2C
    (per this file's own inventory) and has no guard of its own, but it
    is not called from shims.cpp AT ALL -- so it is not a live hole,
    only a dead method that would need a guarded entry point the day
    something starts calling it. If this starts failing because
    shims.cpp now calls resetTracking() somewhere, that call site needs
    a busGuard.acquire()/release() pair of its own before this test's
    assertion is updated to match."""
    assert "resetTracking" not in _SHIMS_STRIPPED, (
        "shims.cpp now references resetTracking() -- it needs its own "
        "busGuard.acquire()/release() pair (see the six guarded entry "
        "points above for the pattern) before this test can be relaxed."
    )
