"""tests/host/test_no_float_format_specifier_in_wire_layer_source_pin.py --
forbids a `%f`/`%.Nf`/`%g`/`%e`-family printf float conversion specifier
in `src/comms/` (the wire/comms layer), in any `std::snprintf`/`snprintf`
call format string.

**Why this exists.** `WireAdapter::execPulse()` (`wire_adapter.cpp`)
formatted its `ret` reply with `%.1f`/`%.2f`. The micro:bit target's
newlib-nano printf has no float conversion support -- not "loses
precision", not "wrong digits", the WHOLE conversion comes back EMPTY.
MEASURED vevov 2026-09-16, team-lead session, over the farm serial link
(null.local:41285), firmware `vevov-nudgehang0915`:

    TX  RUN pulse 25 0 1 #21
    RX  ack 21 9 stop
    RX  ret left_counts= right_counts= left_mm= right_mm= #21

Every field NAME was present; every VALUE was empty. The pulse itself
executed correctly (camera measured ~1.55 cm of arc over 21 pulses,
~0.74 mm each; `cyc` advanced normally) -- only the reporting was
broken, which made the verb useless for the ticket 003 characterization
gate that depends on the encoder counts. Every OTHER wire formatter in
this codebase already avoids float conversions for exactly this reason
-- `wire_handler.cpp`'s `formatConfigValue()` does its own six-digit
fixed-point formatting with integer arithmetic specifically because
"newlib-nano's printf ... has no %f" (that function's own comment).
`execPulse()` was the one holdout that reached hardware before anyone
noticed.

**Why a host test alone cannot catch this.** `tests/host/` links
against the DESK's own libc, whose `printf` genuinely supports `%f` --
`test_wire_motion_verbs.py`'s pulse round-trip test passed on the host
with the broken format string, because on the host `%.1f` correctly
formats a float. The bug is invisible from the host side by
construction; only a source-level pin (this file) or an on-target run
can catch it. This is the same shape
`test_no_percent_z_format_specifier_source_pin.py` documents for `%zu`,
and the same shape `test_vfp_guard_source_pin.py` documents for a bare
`fiber_sleep()` -- a class of defect where the host's own toolchain is
strictly more capable than the target's, so passing host tests prove
nothing about it.

**What this cannot do.** Text matching, not a parser: it cannot
confirm a matched `%f`-family specifier is inside an actual format
string literal passed to a formatting call versus some other string
constant, and it does not understand scope. In practice every hit this
test has ever found was in fact a real `snprintf` format string --
narrow the pattern here rather than adding a broad allow-list entry if
that ever stops being true.

**Scope.** `src/comms/` only (the wire/comms layer: `wire_adapter.cpp`/
`.h`, `wire_handler.cpp`/`.h`, `protocol.cpp`/`.h`, the transport files,
etc.) -- this is the layer that formats wire replies for the on-target
newlib-nano printf, and the layer this defect was found in. Unlike
`test_no_percent_z_format_specifier_source_pin.py`'s repo-wide `src/`
scope, this test does not need to cover `src/core/` (the vendored
kernel never formats a wire reply) or `src/motion/`/`src/platform/`
(no snprintf-based wire formatting lives there); narrow the directory
set here if a future wire formatter moves outside `src/comms/`.

Run with::

    uv run pytest tests/host/test_no_float_format_specifier_in_wire_layer_source_pin.py
"""
import pathlib
import re

# tests/host/test_no_float_format_specifier_in_wire_layer_source_pin.py
# -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_COMMS = _REPO_ROOT / "src" / "comms"

# Matches a printf float conversion: `%`, optional flags/width/precision,
# optional length modifier, then one of f/F/g/G/e/E. Covers `%f`, `%.1f`,
# `%.2f`, `%5.2f`, `%-8.3f`, `%g`, `%e`, `%Lf`, `%lf` -- every spelling
# newlib-nano refuses to convert on this target.
_FLOAT_SPEC_RE = re.compile(
    r"%[-+ 0#]*[0-9]*(?:\.[0-9]+)?(?:hh|ll|[hlL])?[fFgGeE]"
)


def _sources():
    for path in sorted(_COMMS.rglob("*")):
        if path.suffix in (".h", ".cpp"):
            yield path


def _code_lines(path):
    """Lines with `//` comments and `/* */` comment blocks stripped --
    see test_vfp_guard_source_pin.py's own `_code_lines()` for the full
    rationale: without this, this very file's (and wire_adapter.cpp's
    fix comment's, and wire_handler.cpp's formatConfigValue() comment's)
    own explanatory prose about `%f` would self-trip the scan."""
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


def test_no_float_conversion_specifier_anywhere_in_wire_layer():
    bad = []
    for path in _sources():
        for n, line in _code_lines(path):
            m = _FLOAT_SPEC_RE.search(line)
            if m:
                rel = path.relative_to(_REPO_ROOT)
                bad.append(f"  {rel}:{n}: {m.group(0)!r}  ({line.strip()!r})")
    assert not bad, (
        f"{len(bad)} float-conversion printf specifier(s) found in "
        "src/comms/ -- this target's embedded newlib-nano printf has NO "
        "float conversion support: %f/%.Nf/%g/%e do not print wrong "
        "digits, they print NOTHING (MEASURED vevov 2026-09-16, sprint "
        "039 ticket 001's reopened defect: WireAdapter::execPulse()'s "
        "ret line came back with every field name present and every "
        "value empty). Use integer-only formatting instead -- round "
        "to the nearest count/unit and print with %d/%ld/%u/%lu, "
        "scaling by a fixed power of ten (e.g. hundredths as an "
        "'_x100' wire field) when sub-integer resolution matters. See "
        "wire_handler.cpp's formatConfigValue() and "
        "wire_adapter.cpp's execPulse() for the two existing "
        "integer-arithmetic patterns to follow:\n" + "\n".join(bad)
    )
