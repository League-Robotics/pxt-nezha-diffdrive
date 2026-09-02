"""tests/host/test_vfp_guard_source_pin.py -- keeps every yield in this
extension routed through the FPU-bank guard.

**Why this file matters more than the guard itself.** The guard is six
call sites; it is trivially undone by anyone who adds a `fiber_sleep()`
without knowing the history. This test is what makes the fix durable,
so its failure messages are written to teach rather than to accuse.

**The hazard.** The firmware is built with the hardware FPU enabled
(`-mfpu=fpv4-sp-d16 -mfloat-abi=softfp`) and CODAL's context switch
saves R0-R12/SP/LR and no VFP registers at all. GCC allocates the
callee-saved bank s16-s31 (= d8-d15) as ordinary spill space -- for
POINTERS as well as floats -- so a fiber parked at a yield can have its
locals overwritten by the next fiber that does arithmetic. MEASURED
gopiv 2026-09-01: the protocol fiber parked an object pointer in s17
across its poll sleep, a tour fiber's PID wrote a wheel speed over it,
and the protocol fiber dereferenced float -25.0f as `this`.

**What this cannot do.** It is text matching, like
`test_wire_constants_drift.py` and `test_boot_banner_source_pin.py`; it
proves the source shape, never the codegen. Confirming that
`vpush.64 {d8-d15}` / `vldm sp!, {d8-d15}` actually surround the yield
needs a disassembler on a built ELF. And it can only see yields that
*name* a yield primitive -- a CODAL call that blocks internally is
invisible to it, which is exactly how the `SYNC_SLEEP` sends were
missed on the first pass.

Run with::

    uv run pytest tests/host/test_vfp_guard_source_pin.py
"""
import pathlib
import re

# tests/host/test_vfp_guard_source_pin.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_GUARD_H = _SRC / "platform" / "vfp_guard.h"
_GUARD_CPP = _SRC / "platform" / "vfp_guard.cpp"

# The vendored kernel is upstream-owned and must stay byte-identical. It
# yields only through the Sleeper interface, so guarding CodalSleeper
# covers it without editing it -- which is the whole reason it can be
# excluded here rather than fixed.
_VENDORED = {_SRC / "core" / "diffdrive.h", _SRC / "core" / "diffdrive.cpp"}

_WHY = (
    "\n\nWHY THIS IS A BUG: the build enables the hardware FPU and CODAL's"
    "\nswap_context saves NO VFP registers. GCC parks pointers -- not just"
    "\nfloats -- in the callee-saved bank d8-d15, so anything a fiber holds"
    "\nthere is destroyed by the next fiber that does arithmetic. MEASURED"
    "\ngopiv 2026-09-01: a pointer came back as float -25.0f and the"
    "\ndereference hard-faulted the board."
    "\n\nFIX: call diffDrive::vfpSafeSleep() / vfpSafeYield() from"
    "\nsrc/platform/vfp_guard.h instead. If you are wrapping a CODAL call"
    "\nthat blocks internally, add a noinline local helper carrying"
    "\nDIFFDRIVE_VFP_BANK_CLOBBER(), as serial_transport.cpp does."
)


def _sources():
    for path in sorted(_SRC.rglob("*")):
        if path.suffix not in (".h", ".cpp") or path in _VENDORED:
            continue
        yield path


def _code_lines(path):
    """Lines with `//` comments and comment blocks stripped.

    Without this the test trips over its own explanatory prose -- the
    hazard is described in comments in several of these files.
    """
    out, in_block = [], False
    for n, raw in enumerate(path.read_text().splitlines(), 1):
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
        line = line.split("//", 1)[0]
        if line.strip():
            out.append((n, line))
    return out


def test_no_bare_fiber_sleep_or_schedule_outside_the_guard():
    bad = []
    for path in _sources():
        if path == _GUARD_CPP:
            continue          # the guard is where these two legally live
        for n, line in _code_lines(path):
            if re.search(r"\bfiber_sleep\s*\(", line) or re.search(
                r"(?<![\w:])schedule\s*\(\s*\)", line
            ):
                bad.append(f"  {path.relative_to(_REPO_ROOT)}:{n}: {line.strip()}")
    assert not bad, (
        "bare yield(s) found -- these bypass the FPU-bank guard:\n"
        + "\n".join(bad)
        + _WHY
    )


def test_sync_sleep_only_reaches_the_wire_through_the_guarded_helper():
    """`SYNC_SLEEP` is a yield that grepping for `fiber_sleep` misses.

    `uBit.serial.send(..., SYNC_SLEEP)` blocks on
    `fiber_wait_for_event()` when CODAL's TX ring fills. It is confined
    to one noinline helper so there is exactly one place to guard.
    """
    sites = []
    for path in _sources():
        for n, line in _code_lines(path):
            if "SYNC_SLEEP" in line:
                sites.append((path, n, line.strip()))
    assert sites, "no SYNC_SLEEP found at all -- has the serial send been rewritten?"
    stray = [
        f"  {p.relative_to(_REPO_ROOT)}:{n}: {t}"
        for p, n, t in sites
        if p.name != "serial_transport.cpp"
    ]
    assert not stray, (
        "SYNC_SLEEP used outside serial_transport.cpp's guarded helper:\n"
        + "\n".join(stray)
        + _WHY
    )
    helper = _GUARD_CPP.parent  # noqa: F841  (kept for symmetry of intent)
    text = (_SRC / "comms" / "serial_transport.cpp").read_text()
    assert "guardedSerialSend" in text and "DIFFDRIVE_VFP_BANK_CLOBBER" in text, (
        "serial_transport.cpp no longer routes SYNC_SLEEP through a helper "
        "carrying DIFFDRIVE_VFP_BANK_CLOBBER()." + _WHY
    )


def test_guard_clobbers_the_whole_callee_saved_bank():
    header = _GUARD_H.read_text()
    missing = [r for r in (f"d{i}" for i in range(8, 16)) if f'"{r}"' not in header]
    assert not missing, (
        f"vfp_guard.h's clobber list is missing {missing}. The bank is "
        "d8-d15 and a partial list leaves the rest unsaved -- the "
        "compiler is free to spill into exactly the registers you left out."
    )


def test_guard_bodies_stay_out_of_line():
    body = _GUARD_CPP.read_text()
    for fn in ("vfpSafeSleep", "vfpSafeYield"):
        pattern = r"__attribute__\(\(noinline\)\)\s+void\s+" + fn
        assert re.search(pattern, body), (
            f"{fn} lost its noinline attribute.\n\nnoinline is what gives the "
            "wrapper its own stack frame, and the frame is where the saved "
            "bank lives. Inlined, GCC hoists the save into the caller's "
            "prologue and then refuses to allocate d8-d15 across the asm for "
            "the whole enclosing function -- still correct, but it degrades "
            "register allocation everywhere and leaves no single symbol to "
            "verify with a disassembler."
        )
