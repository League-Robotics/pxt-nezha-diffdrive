"""tests/host/test_no_percent_z_format_specifier_source_pin.py -- forbids
a `%z`-family printf conversion specifier (`%zu`, `%zd`, `%zx`, ...) in
any target-compiled source under `src/`.

**Why this exists.** `%zu` is not supported by this target's printf --
MEASURED gopiv 2026-09-09, `captures/wifi-credential-store-20260909/`:
`WireHandler::execWifiCred()`'s bare-enumeration `snprintf(buf,
sizeof(buf), "wificred %zu %s %d\n", i, ...)` produced the literal wire
line `wificred zu 0` instead of `wificred 0 TestNet038 1` -- the
embedded newlib-nano printf does not recognize `z` as a length
modifier, emits the two characters `zu` verbatim, and every remaining
`snprintf` argument shifts left by one slot. This is exactly the same
family of newlib-nano gap `protocol.cpp`/`wifi_link.cpp`/
`wire_handler.cpp` already carry comments about for `std::snprintf`
and float formatting.

**Why a host test can miss this.** `tests/host/` links against the
DESK's own libc, whose `printf` genuinely does support `%zu` --
`tests/host/test_wire_grammar.py::test_wificred_golden_vector` passed
before this bug was fixed, because on the host `%zu` correctly consumes
one `size_t` and prints it as expected. The bug is invisible from the
host side by construction; only a source-level pin (this file) or an
on-target run can catch it. So: cast to `unsigned` (or `int`) and use
`%u`/`%d`, the convention `WireHandler::replyErr()` already uses for a
size-typed value (`static_cast<unsigned>(code)`), never `%zu`/`%zd`/
`%zx` directly on a `size_t`.

Modeled on `test_no_units_in_identifiers_source_pin.py`'s pattern: a
repo-wide grep-based pytest, comments stripped first so the test does
not trip over ITS OWN explanatory prose above (and this file's, and
wire_handler.cpp's fix-comment, both of which say "%zu" in English) --
comment-stripping is what keeps this test honest rather than
self-defeating.

**Scope.** All of `src/` -- every translation unit in this tree is
ultimately compiled for the embedded target (there is no host build of
firmware code; `tests/host/` compiles isolated, host-portable pieces
against shims, never the target toolchain's own newlib-nano). Unlike
`test_no_units_in_identifiers_source_pin.py` this does NOT exclude
`src/core/` (the vendored kernel) -- a `%z` specifier there would be
just as broken on this target, and vendored code is still compiled for
it; this test simply has never had a reason to touch that directory
because the kernel does not have this defect (nothing in `src/core/`
formats a `size_t`).

Run with::

    uv run pytest tests/host/test_no_percent_z_format_specifier_source_pin.py
"""
import pathlib
import re

# tests/host/test_no_percent_z_format_specifier_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"

# Matches the length-modifier form (%z + one more length char, e.g. %zu
# converts as: z length modifier, u conversion) as well as a bare %z
# immediately followed by a conversion letter -- covers %zu/%zd/%zx/%zo
# and any other conversion letter someone might pair it with.
_PERCENT_Z_RE = re.compile(r"%[-+ 0#]*[0-9]*z[a-zA-Z]")


def _sources():
    for path in sorted(_SRC.rglob("*")):
        if path.suffix in (".h", ".cpp"):
            yield path


def _code_lines(path):
    """Lines with `//` comments and `/* */` comment blocks stripped --
    see test_vfp_guard_source_pin.py's own `_code_lines()` for the full
    rationale: without this, this very file's (and wire_handler.cpp's
    fix comment's) own explanatory prose about `%zu` would self-trip
    the scan."""
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


def test_no_percent_z_conversion_specifier_anywhere_in_src():
    bad = []
    for path in _sources():
        for n, line in _code_lines(path):
            m = _PERCENT_Z_RE.search(line)
            if m:
                rel = path.relative_to(_REPO_ROOT)
                bad.append(f"  {rel}:{n}: {m.group(0)!r}")
    assert not bad, (
        f"{len(bad)} '%z'-family printf specifier(s) found in src/ -- "
        "this target's embedded newlib-nano printf does NOT support the "
        "'z' length modifier (MEASURED gopiv 2026-09-09, "
        "captures/wifi-credential-store-20260909/: it emits 'zu' "
        "literally and shifts every later argument). Cast the size_t "
        "value to unsigned/int and use %u/%d instead, per "
        "WireHandler::replyErr()'s own precedent:\n" + "\n".join(bad)
    )
