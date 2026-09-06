"""tests/host/test_cyclestat_deleted.py -- sprint 032 ticket 008,
extended by sprint 033 ticket 001.

`cycleStat()` (`src/shims.cpp`) and its simulator stand-in `_cycleStat()`
(`src/blocks/sim.ts`) had no caller anywhere in `src/`, `test/`,
`tests/`, or `tools/` -- grepped repo-wide, not assumed (confirmed
again by this test, which fails if either name resurfaces). Both are
deleted entirely, along with the `//% shim=diffDrive::cycleStat`
annotation and `sim.ts`'s comment describing it.

Sprint 032 ticket 008 deliberately left `r.tickOverrunCount`
(`shims.cpp`) and `simCycleCount`/`simTickOverrunCount` (`sim.ts`) in
place, as out of scope, even though `cycleStat()`'s deletion made them
write-only: still incremented every tick by
`tickDrive()`/`_tickDrive()`'s own pacing logic, read by nothing.
Sprint 033 ticket 001 made the deliberate decision to delete them too
(the alternative -- wiring up a real reader behind a new diag ordinal
-- was rejected as not worth it absent an actual need for a
Rig-level tick-overrun diagnostic distinct from the kernel's own).
All three names, and their per-tick increments, are now gone from
`src/shims.cpp` and `src/blocks/sim.ts`; this test asserts they stay
gone the same way it already asserted `cycleStat` stays gone.

The kernel's own missed-deadline counter (`out.cycleOverrunCount`,
`diagValue()` case 19, `src/core/diffdrive.h`/`.cpp`) is a distinct,
real quantity with a real reader (`probe(19)`) and is untouched by
either ticket.

Run with::

    uv run pytest tests/host/test_cyclestat_deleted.py
"""

import pathlib

# tests/host/test_cyclestat_deleted.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_SCAN_DIRS = ("src", "test", "tests", "tools")
_SCAN_SUFFIXES = (".ts", ".cpp", ".h", ".py")


def _all_source_files():
    for d in _SCAN_DIRS:
        root = _REPO_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in _SCAN_SUFFIXES:
                # This test file's own docstring/name legitimately
                # mentions the deleted name -- exclude it from the scan
                # of itself.
                if p == pathlib.Path(__file__).resolve():
                    continue
                yield p


def test_cyclestat_has_zero_references_in_source_and_tests():
    hits = {}
    for p in _all_source_files():
        text = p.read_text(errors="ignore")
        if "cycleStat" in text:
            hits[str(p.relative_to(_REPO_ROOT))] = text.count("cycleStat")
    assert not hits, (
        "cycleStat/_cycleStat must have zero references in src/test/"
        "tests/tools after its deletion -- found: %r" % hits
    )


# Sprint 033 ticket 001: the write-only counters cycleStat() used to
# read, deleted along with their per-tick increments. See this file's
# module docstring for the decision record.
_DEAD_TICK_OVERRUN_NAMES = (
    "tickOverrunCount",
    "simCycleCount",
    "simTickOverrunCount",
)


def test_dead_tick_overrun_counters_have_zero_references_in_source_and_tests():
    hits = {}
    for p in _all_source_files():
        text = p.read_text(errors="ignore")
        found = [name for name in _DEAD_TICK_OVERRUN_NAMES if name in text]
        if found:
            hits[str(p.relative_to(_REPO_ROOT))] = found
    assert not hits, (
        "tickOverrunCount/simCycleCount/simTickOverrunCount must have zero "
        "references in src/test/tests/tools after sprint 033 ticket 001 "
        "deleted them as dead (write-only, read by nothing) state -- "
        "found: %r" % hits
    )


def test_kernel_cycle_overrun_count_diag_ordinal_19_is_untouched():
    """The near-miss this ticket must not step on.

    `diagValue()` case 19 / `out.cycleOverrunCount` is the KERNEL's own
    missed-deadline count (`src/core/diffdrive.h`/`.cpp`), a distinct,
    real quantity with a real reader (`probe(19)`). It is not one of
    the dead Rig-level counters this file's other test deletes, and
    must survive unchanged.
    """
    shims_cpp = (_REPO_ROOT / "src" / "shims.cpp").read_text()
    assert "case 19: return static_cast<int>(out.cycleOverrunCount);" in shims_cpp, (
        "diagValue() case 19 / out.cycleOverrunCount is missing or changed -- "
        "this is the kernel's real missed-deadline counter, not the dead "
        "Rig-level counters this file deletes. It must stay untouched."
    )
