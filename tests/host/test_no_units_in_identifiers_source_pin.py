"""tests/host/test_no_units_in_identifiers_source_pin.py -- keeps units
out of identifier names in project-owned `src/` (outside the vendored
kernel) and `test/test.ts`, per `.claude/rules/no-units-in-identifiers.md`:
a method, field, parameter or local is named for *what it is*, never for
the unit it happens to be measured in -- the unit belongs in a trailing
`// [unit]` comment on the declaration.

Modeled on `test_vfp_guard_source_pin.py`'s pattern: a grep-based pytest
that fails the build on a forbidden source shape, with comments stripped
first so the test does not trip over its own explanatory prose (this
project's comments routinely narrate a PAST rename, e.g. "renamed from
dominantAxisTravelMm()" -- narrating that history is not the same defect
as a live identifier still carrying the unit).

**What counts as a violation.** Any identifier (method, field, parameter,
local, or constant) whose name ends in one of this project's unit
suffixes -- `MmS2`/`MmS3`/`DegS`/`Cdeg`/`Counts`/`MmS`/`Rad`/`Deg`/`Mm`/
`Ms`/`Us`/`Pct` -- with at most one trailing underscore (this project's
own member-field convention, e.g. `defaultCruise_`). Suffixes are
matched longest-first so `aDecelMmS2` reports as an `MmS2` hit, not a
spurious `Mm` hit one character short.

**What this cannot do.** Same limitation `test_vfp_guard_source_pin.py`'s
own docstring names: this is text matching, not a parser -- it cannot
tell a real identifier from a string literal that happens to contain the
same shape, and it does not understand scope. In practice this project's
own wire-protocol/JSON field names are snake_case (`v_max`, `stop_distance`)
and never collide with the camelCase suffixes this test matches, so that
gap has not mattered in practice; if it ever does, narrow the pattern
here rather than papering over a real hit with a broader allow-list
entry.

Run with::

    uv run pytest tests/host/test_no_units_in_identifiers_source_pin.py
"""
import pathlib
import re

# tests/host/test_no_units_in_identifiers_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_TEST_TS = _REPO_ROOT / "test" / "test.ts"

# The vendored kernel is upstream-owned and excluded by
# .claude/rules/no-units-in-identifiers.md itself ("Where the unit goes
# instead" / the kernel-style exception this project inherited rather
# than authored) -- byte-identity with upstream is a standing invariant
# (fiber-yield-safety.md), so this ticket does not, and must not, touch it.
_EXCLUDED_DIRS = {_SRC / "core"}

# src/comms/wifi_link.{h,cpp} -- NOT this ticket's scope. The WiFi
# transport (merged 2026-09-03, af74da8/99d72c5, AFTER the
# strip-units-from-identifier-names issue's own ~520-occurrence
# inventory was taken) carries ~70 of its own MmS/Ms-suffixed names
# (kCommandTimeoutMs, nowMs_, lastPeerHeardMs_, ...) that this ticket's
# dispatcher-given scope deliberately does not list alongside
# wire_handler/wire_adapter/serial_transport/radio_transport/protocol/
# run_queue/emit_queue. wifi_uart.{h,cpp} (the same transport's UART
# half) is already clean and needs no exclusion. Tracked as follow-up
# scope, not fixed here -- excluding it is what keeps this pin test
# truthful about what THIS ticket actually cleaned up, rather than
# quietly widening the ticket's own scope by relaxing the test instead
# of the code.
_EXCLUDED_FILES = {
    _SRC / "comms" / "wifi_link.h",
    _SRC / "comms" / "wifi_link.cpp",
}

# Suffixes, longest first so e.g. "MmS2" is reported as itself rather
# than matching the shorter "Mm"/"Ms" alternatives one character short.
_SUFFIXES = (
    "MmS2", "MmS3", "DegS", "Cdeg", "Counts", "MmS", "Rad", "Deg", "Mm",
    "Ms", "Us", "Pct",
)
_UNIT_SUFFIX_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:" + "|".join(_SUFFIXES) + r")_?\b"
)
_SUFFIX_RE = re.compile("(?:" + "|".join(_SUFFIXES) + r")_?$")

# ---- allow-list: named conversion functions/constants whose entire job
# IS the unit conversion (no-units-in-identifiers.md's own "Where the
# unit goes instead" section names this exact carve-out: "A boundary
# that *converts* units is a named function whose name says the
# conversion"). One line each -- why this specific name earns the
# exception, not a blanket category.
_ALLOWED = {
    # wire's milliradian integer -> the kernel/motion-engine's own
    # radian scale (wire_adapter.cpp) -- named explicitly in the ticket.
    "mradToRad": "conversion function: milliradians -> radians (wire_adapter.cpp)",
    # shaft counts -> millimetres of travel (motion_engine.h, called
    # throughout shims.cpp/wire_adapter.cpp as r.engine.countsPerMm()) --
    # named explicitly in the ticket.
    "countsPerMm": "conversion function: counts -> mm (motion_engine.h)",
    # writes an OTOS pose register triplet already mm-scaled -- named
    # explicitly in the ticket.
    "writePoseMm": "conversion/write function: pose in mm scale (otos_port.cpp)",
    # MotionLimits' own omega ceilings, expressed as an equivalent wheel
    # speed for a given track width -- the "As" IS the conversion.
    "omegaFloorAsWheelSpeed": "conversion function: omega floor -> wheel speed (motion_limits.h)",
    "omegaMaxAsWheelSpeed": "conversion function: omega ceiling -> wheel speed (motion_limits.h)",
    # shims.cpp's one wire/kernel boundary-scale constant pair: the
    # wire's centidegree integers <-> the kernel/motion-engine's radians.
    "kCdegToRad": "conversion constant: centidegrees -> radians (shims.cpp)",
    "kRadToCdeg": "conversion constant: radians -> centidegrees (shims.cpp)",
    # motion/'s own geometry conversions (out of this ticket's rename
    # scope -- ticket 003's own work -- but in this test's scan scope,
    # since the pin test covers all of src/ outside src/core/).
    "mmPerDeg": "conversion function: degrees -> mm of wheel travel (motion_engine.h)",
    "kDegToRad": "conversion constant: degrees -> radians (motion_limits.h)",
    # RETIRED PXT `//%` shim (shims.cpp), its TS simulator twin
    # (blocks/sim.ts), and its test/test.ts callers: kept byte-identical
    # on purpose so a MakeCode project saved before sprint 029 that still
    # calls `setRampMs(...)` compiles and runs as a no-op -- see the
    # RETIRED comment above the shim in shims.cpp. Renaming the NAME
    # (unlike its now-bare parameters) would break exactly the backward
    # compatibility this shim exists to provide -- the same reasoning
    # this project's own wire field names are excluded from this rule
    # entirely (no-units-in-identifiers.md: "Wire field names ... follow
    # their own file's convention; this rule is about code identifiers"),
    # just for one C++/TS function name instead of a wire key.
    "setRampMs": "retained PXT shim name: backward compat for pre-sprint-029 saved projects (shims.cpp/sim.ts/test.ts)",
}


def _sources():
    for path in sorted(_SRC.rglob("*")):
        if path.suffix not in (".h", ".cpp", ".ts"):
            continue
        if path in _EXCLUDED_FILES:
            continue
        if any(excluded in path.parents for excluded in _EXCLUDED_DIRS):
            continue
        yield path
    yield _TEST_TS


def _code_lines(path):
    """Lines with `//` comments and `/* */` comment blocks stripped --
    see test_vfp_guard_source_pin.py's own `_code_lines()` for why:
    without this the test trips over its own explanatory prose (this
    project's comments routinely narrate a past rename by its old name)."""
    out, in_block = [], False
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw
        if in_block:
            if "*/" in line:
                line, in_block = line.split("*/", 1)[1], False
            else:
                continue
        while "/*" in line:
            head, _, rest = line.partition("/*")
            if "*/" in rest:
                line = head + rest.split("*/", 1)[1]
            else:
                line, in_block = head, True
                break
        line = line.split("//", 1)[0]
        out.append((n, line))
    return out


def _suffix_of(identifier: str) -> str:
    m = _SUFFIX_RE.search(identifier)
    return m.group(0) if m else "?"


def test_no_unit_suffixed_identifiers_outside_core_and_allowlist():
    bad = []
    for path in _sources():
        for n, line in _code_lines(path):
            for m in _UNIT_SUFFIX_RE.finditer(line):
                name = m.group(0)
                if name in _ALLOWED:
                    continue
                rel = path.relative_to(_REPO_ROOT)
                bad.append(f"  {rel}:{n}: {name}  (suffix: {_suffix_of(name)})")
    assert not bad, (
        f"{len(bad)} unit-suffixed identifier(s) found outside src/core/ "
        "and the allow-list -- move the unit into a trailing `// [unit]` "
        "comment on the declaration instead (.claude/rules/"
        "no-units-in-identifiers.md):\n" + "\n".join(bad)
    )


def test_allowlist_has_no_stale_entries():
    """Every allow-listed name must actually appear somewhere in the
    scanned source (as a real identifier, not necessarily one that
    itself matches `_UNIT_SUFFIX_RE` -- `omegaFloorAsWheelSpeed`/
    `omegaMaxAsWheelSpeed` are listed per the ticket's own explicit
    instruction even though they end in "Speed", not a unit suffix, so
    they never trip the main test either way) -- an allow-list entry for
    a name nothing uses any more is exactly the kind of silent drift
    measurement-citations.md warns about: it stops meaning anything and
    nobody notices."""
    name_re = {
        name: re.compile(r"\b" + re.escape(name) + r"\b") for name in _ALLOWED
    }
    seen = set()
    for path in _sources():
        for _, line in _code_lines(path):
            for name, pattern in name_re.items():
                if name not in seen and pattern.search(line):
                    seen.add(name)
    stale = sorted(name for name in _ALLOWED if name not in seen)
    assert not stale, (
        "allow-listed name(s) no longer appear anywhere in the scanned "
        "source -- remove the stale entry/entries: " + ", ".join(stale)
    )
