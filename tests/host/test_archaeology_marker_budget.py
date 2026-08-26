"""tests/host/test_archaeology_marker_budget.py -- a ratchet guard
against comment archaeology: sprint numbers, ticket numbers,
code-review finding IDs, and design-doc filenames accreting inside
`src/` comments, restating what git already knows for free.

Modeled directly on `test_pxt_manifest_completeness.py`: no compiler,
reads files as text, milliseconds.

**Why a ratchet, not a cleanup.** Sprint 009 ran a dedicated comment
cleanup sprint and cut the codebase's comment volume by ~470 lines
(8%). By sprint 013, every file that cleanup touched had grown back
PAST its pre-cleanup line count -- a cleanup with no write-time rule
behind it does not hold; the volume just regrows under the next round
of tickets. This test is the write-time backstop:
`docs/code-review/guidelines.md`'s new "Write-time standard" section
(this same ticket) tells an author what to write; this test makes a
regression in the OPPOSITE direction (comments accreting archaeology
instead of stating facts) fail CI instead of waiting for the next
audit to notice.

**What counts as a marker.** A comment line containing `sprint N`,
`ticket N`, `R-NN`, `KERN-NN`, `WIRE-NN`, `BLK-NN`, `API-NN`, `MOD-NN`,
`DES-NN`, `PY-NN`, or any `<name>.md` filename mention. This is the
broader regex from `docs/code-review/2026-08-26/raw/comment-audit.md`
section 5 (the audit that produced the original 363 baseline), not the
narrower one sketched in that document's section 9 -- the broader one
is what actually produced the baseline number, so it's the one this
test replicates for an apples-to-apples ratchet. It deliberately does
NOT try to distinguish a marker that is genuinely archaeological
("closes ticket 004") from one that is a live spec citation
("motion-api.md S3.6") -- that was the audit's own methodology, and
this ticket's job is to measure and ratchet it, not redesign it (a
bulk cleanup, including any reclassification of what should count, is
explicitly out of scope -- see the source ticket).

**Vendored kernel excluded.** `src/core/diffdrive.{h,cpp}` is upstream
(`League-Robotics/radio-robot`) code this project does not edit for
style; the audit measured 2 marker lines there, and this test excludes
it from both the count and the budget the same way.

**The budget only ratchets down.** Raising `_BUDGET` requires an
explicit, reviewed edit to this file's constant -- never a silent
increase. Lowering it (after a real cleanup sprint, the kind this
ticket deliberately does NOT attempt) is always welcome.

Run with::

    uv run pytest tests/host/test_archaeology_marker_budget.py
"""

import pathlib
import re

# tests/host/test_archaeology_marker_budget.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

# Vendored kernel -- upstream-owned, not subject to this project's
# comment standard. See the module docstring.
_EXCLUDED = {_SRC_DIR / "core" / "diffdrive.h", _SRC_DIR / "core" / "diffdrive.cpp"}

_SOURCE_SUFFIXES = (".h", ".cpp", ".ts")

# The broader marker set from comment-audit.md section 5 (produced the
# 363 baseline) -- section 9's `_MARKERS` sketch omits MOD-NN/DES-NN/
# PY-NN/`.md` filenames; this includes them, per that section's own
# note that the broader regex is what the baseline number reflects.
_MARKERS = re.compile(
    r"\bsprint \d|\bticket \d|\bR-\d\d|KERN-\d\d|WIRE-\d\d|BLK-\d\d|API-\d\d|"
    r"MOD-\d\d|DES-\d\d|PY-\d\d|\b[\w-]+\.md\b",
    re.I,
)

# Measured 2026-08-26 against the tree as of sprint 017 ticket 005
# (this ticket's own predecessor in the same sprint) -- 388, not the
# 2026-08-26 audit's original 363. The gap is real drift, not a
# methodology difference: re-running the audit's own broader regex,
# scoped the same way (excluding the vendored kernel), against the
# CURRENT tree reproduces most per-file counts from the audit almost
# exactly (e.g. `wire_handler.h` 47/47, `motion_engine.h` 37/37,
# `radio_transport.h` 20/20 -- both exact) with the rest higher by a
# handful of lines each, consistent with ordinary comment edits across
# sprints 015-017 landing between the audit and this measurement, not
# a scanning discrepancy. Ratchets DOWN only from here -- see the
# module docstring.
_BUDGET = 388


def _marker_line_count():
    total = 0
    per_file = {}
    for p in sorted(_SRC_DIR.rglob("*")):
        if not p.is_file() or p.suffix not in _SOURCE_SUFFIXES or p in _EXCLUDED:
            continue
        lines = p.read_text(errors="ignore").splitlines()
        count = sum(1 for line in lines if _MARKERS.search(line))
        if count:
            per_file[str(p.relative_to(_REPO_ROOT))] = count
        total += count
    return total, per_file


def test_archaeology_marker_count_is_within_budget():
    """Comment lines across project-owned `src/` (vendored
    `core/diffdrive.{h,cpp}` excluded) carrying a sprint/ticket/
    finding-ID/`.md`-filename marker must not exceed the ratchet
    budget. A failure here means a change added archaeology comments
    faster than anything removed them -- either cut the new ones (put
    the sprint/ticket reference in the commit message instead, per
    `docs/code-review/guidelines.md`'s write-time standard) or, if the
    budget is being deliberately raised, do that as its own reviewed
    edit to `_BUDGET` above, not incidentally."""
    total, per_file = _marker_line_count()
    assert total <= _BUDGET, (
        f"archaeology-marker count {total} exceeds the ratchet budget "
        f"of {_BUDGET} -- per-file counts: {per_file}"
    )
