"""tests/host/test_kblock_ownership_source_pin.py -- pins kBlock
motion-owner coverage across `src/shims.cpp` (sprint 030 ticket 002,
clasi/sprints/030-bus-discipline-and-fiber-safety/issues/
service-hook-must-check-fiber-identity.md).

**What this is NOT.** Source-text pinning, following
`test_bus_guard_source_pin.py`'s own precedent (itself following
`test_run_abort_source_pin.py`'s/`test_vfp_guard_source_pin.py`'s) of
regex-asserting on source text without compiling it -- `tests/host/`
cannot compile `shims.cpp` at all (it includes `pxt.h`, directly and
transitively). It cannot prove a real CODAL fiber calling one of these
entry points is actually refused on real hardware, only that the source
shape which makes that possible is present.
`tests/host/test_motion_owner.py` is what proves the underlying
take/release ARBITRATION logic is correct, in isolation (the pure
functions in `src/core/motion_owner.h`); this file proves shims.cpp's
own entry points actually call it.

**The three take sites and the five release sites.** The ticket's own
Remedy names four block-motion entry points -- startMove(), startGoTo(),
driveTwist(), startDrive() -- but only three of those are shims.cpp
functions of their own: startGoTo() (blocks/motion.ts) reaches the
engine through engineGoToRArmed(), and startDrive() (blocks/motion.ts)
reaches it by calling the SAME block-facing driveTwist() this file also
checks -- taking ownership there covers both TS-level callers with one
guarded C++ entry point. Release happens wherever a block motion's own
span can end: tickDrive() (the ordinary case, once the drivetrain next
looks idle), the starvation watchdog (an abandoned call that was never
ticked at all), and the three explicit stop paths (endMove()/stopAll()/
estopAll()).

**Known, deliberately out-of-scope gap.** setWheels() (setWheelSpeeds()
in blocks/motion.ts) is the same continuous-mode shape as driveTwist()
but is NOT one of the ticket's named entry points and is not gated
here -- a continuous `setWheelSpeeds()` call can still supersede a live
wire/job move with no arbitration. Flagged in the ticket's own report,
not fixed by this ticket.

Run with::

    uv run pytest tests/host/test_kblock_ownership_source_pin.py
"""
import pathlib
import re

import pytest

# tests/host/test_kblock_ownership_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS_CPP = _REPO_ROOT / "src" / "shims.cpp"


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

# {label: signature regex} -- the three take sites (covers all four of
# the ticket's named entry points, per this file's own header comment).
_TAKE_SITES = {
    "driveTwist": r"\bvoid\s+driveTwist\s*\(\s*int\s+speed,\s*int\s+yawRate\s*\)\s*\{",
    "startMove": (
        r"\bvoid\s+startMove\s*\(\s*int\s+distance,\s*int\s+yaw,\s*int\s+speed,"
        r"\s*int\s+yawRate\s*\)\s*\{"
    ),
    "engineGoToRArmed": (
        r"\bvoid\s+engineGoToRArmed\s*\(\s*float\s+x,\s*float\s+y,"
        r"\s*float\s+speed,\s*float\s+arrive\s*\)\s*\{"
    ),
}

# {label: signature regex} -- the five release sites.
_RELEASE_SITES = {
    "tickDrive": r"\bbool\s+tickDrive\s*\(\s*\)\s*\{",
    "watchdogEntry": r"\bstatic\s+void\s+watchdogEntry\s*\(\s*void\*\s*context\s*\)\s*\{",
    "endMove": r"\bvoid\s+endMove\s*\(\s*\)\s*\{",
    "stopAll": r"\bvoid\s+stopAll\s*\(\s*\)\s*\{",
    "estopAll": r"\bvoid\s+estopAll\s*\(\s*\)\s*\{",
}


@pytest.mark.parametrize("name", sorted(_TAKE_SITES.keys()))
def test_block_motion_entry_point_takes_kblock_ownership(name):
    """Each of these three entry points must call
    protocolTryTakeBlockOwnership() -- and, per the ticket's own
    arbitration decision, must check its result (a refusal must not
    fall through and command the engine anyway)."""
    body = _function_body(_SHIMS_STRIPPED, _TAKE_SITES[name], name)
    assert re.search(r"protocolTryTakeBlockOwnership\s*\(\s*\)", body), (
        f"{name}(): body has no protocolTryTakeBlockOwnership() call:\n{body}"
    )
    assert re.search(
        r"if\s*\(\s*!\s*protocolTryTakeBlockOwnership\s*\(\s*\)\s*\)\s*return",
        body,
    ), (
        f"{name}(): protocolTryTakeBlockOwnership()'s result is not "
        f"checked with an early return -- a refusal must not fall "
        f"through to the engine call:\n{body}"
    )


@pytest.mark.parametrize("name", sorted(_RELEASE_SITES.keys()))
def test_stop_or_idle_path_releases_kblock_ownership(name):
    """Each of these five paths -- the ordinary tick-driven idle
    transition, the abandoned-call safety net, and the three explicit
    stop verbs -- must call protocolReleaseBlockOwnership() so kBlock
    can never outlive the motion it was taken for."""
    body = _function_body(_SHIMS_STRIPPED, _RELEASE_SITES[name], name)
    assert re.search(r"protocolReleaseBlockOwnership\s*\(\s*\)", body), (
        f"{name}(): body has no protocolReleaseBlockOwnership() call:\n{body}"
    )


def test_setwheels_is_a_documented_gap_not_a_silent_one():
    """setWheelSpeeds()'s own shim, setWheels(), is deliberately NOT
    gated (see this file's own module docstring) -- pinned here so a
    future reader who adds arbitration to it updates this test
    deliberately, rather than the gap silently closing (or reopening)
    unnoticed."""
    body = _function_body(
        _SHIMS_STRIPPED,
        r"\bvoid\s+setWheels\s*\(\s*int\s+left,\s*int\s+right\s*\)\s*\{",
        "setWheels",
    )
    assert "protocolTryTakeBlockOwnership" not in body
