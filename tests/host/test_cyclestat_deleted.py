"""tests/host/test_cyclestat_deleted.py -- sprint 032 ticket 008.

`cycleStat()` (`src/shims.cpp`) and its simulator stand-in `_cycleStat()`
(`src/blocks/sim.ts`) had no caller anywhere in `src/`, `test/`,
`tests/`, or `tools/` -- grepped repo-wide, not assumed (confirmed
again by this test, which fails if either name resurfaces). Both are
deleted entirely, along with the `//% shim=diffDrive::cycleStat`
annotation and `sim.ts`'s comment describing it.

`r.tickOverrunCount` (`shims.cpp`) and `simCycleCount`/
`simTickOverrunCount` (`sim.ts`) are deliberately left in place: they
are still written every tick by `tickDrive()`/`_tickDrive()`'s own
pacing logic, independent of `cycleStat()` ever existing to read them
-- this ticket's scope is the dead reader, not those counters.

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
