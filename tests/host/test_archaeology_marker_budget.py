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

Second ratchet: comment VOLUME
------------------------------

The marker ratchet above catches *archaeology* -- sprint numbers,
ticket numbers, finding IDs. It does not catch *length*. The
2026-09-02 review found the growth since the 2026-08-26 review took a
different shape entirely: dated capture citations and stacked UPDATE
paragraphs, carrying no sprint number at all, and therefore invisible
to `_MARKERS`. The volume grew while the marker count sat comfortably
under `_BUDGET`.

So this module asserts TWO independent things, deliberately not fused
into one score: marker count (archaeology) and comment-lines per
code-line (length). A fused metric would let one mask the other, which
is exactly how the growth between the two reviews went unnoticed.

**The counting rule.** A line is a COMMENT line iff, stripped of
leading whitespace, it begins with ``//`` and does NOT begin with
``//%``. Every other non-blank line is a CODE line. Blank lines count
as neither. Three exclusions fall out of that rule and are
load-bearing; a future reader cannot recover the reasons from the code,
so they are stated here:

1. **``//%`` is CODE, not comment.** Those are PXT block pragmas
   (``//% block=``, ``//% group=``, ``//% weight=``) -- 202 such lines
   across `src/blocks/*.ts` and 41 in `src/shims.cpp` and
   `src/comms/protocol.cpp`. They are required block metadata that PXT
   reads to build the toolbox. A ratchet that counted them would
   pressure an author into deleting them to get under a baseline.
2. **``/** ... */`` JSDoc is not counted.** The rule already excludes it
   (it does not start with ``//``), but the reason matters: JSDoc on the
   block API is the student-facing documentation PXT renders into the
   toolbox and the hover help. It is a deliverable, not archaeology, and
   must never be under ratchet pressure.
3. **A trailing ``// [mm]`` on a line of code is not counted.** The rule
   inspects only the START of the stripped line. This is deliberate:
   `.claude/rules/no-units-in-identifiers.md` makes the trailing
   ``// [unit]`` comment on a declaration the house style, replacing
   units baked into identifier names. The ratchet must never make an
   author choose between it and a baseline.

The vendored kernel is excluded here exactly as it is from the marker
ratchet -- same `_EXCLUDED` set, same reason.

**Per-file baselines, not a blanket cap.** A blanket cap was considered
at planning time and rejected. A cap of 2.0 would fail
`src/core/fiber_identity.h` (7 code lines) and `src/core/heading_wrap.h`
(11 code lines) forever -- a header that states a contract, a unit and
one measured fact is above 2.0 no matter how tightly it is written --
while letting `src/comms/wire_adapter.h`, 5.46 at the seed measurement,
sit at 1.99 unchallenged. The ratio is only meaningful against the same
file's own past, so the baseline is per-file and seeded from
measurement.

**A file absent from `_RATIO_BASELINE` is not failed.** A newly added
`src/` file has no baseline and cannot regress against one. The test
asserts only over the files present in the dict and reports the missing
ones as a note in the failure message, so the gap stays visible.

**Ratchets down only**, same discipline as `_BUDGET`: raising an entry
is an explicit reviewed edit to the dict below, never incidental.

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

# RE-SEEDED 2026-09-06 (sprint 035 ticket 008): 388 -> 173.
#
# The previous value, 388, was measured 2026-08-26 against the tree as
# of sprint 017 ticket 005 -- not the 2026-08-26 audit's original 363.
# That gap was real drift, not a methodology difference: re-running the
# audit's own broader regex, scoped the same way (excluding the vendored
# kernel), reproduced most per-file counts from the audit almost exactly
# (e.g. `wire_handler.h` 47/47, `motion_engine.h` 37/37,
# `radio_transport.h` 20/20 -- both exact) with the rest higher by a
# handful of lines each, consistent with ordinary comment edits across
# sprints 015-017.
#
# 173 is what the tree measures after sprint 035's comment work order
# (tickets 002-006) deleted the archaeology those markers were sitting
# in. It is the MEASURED post-cleanup count, not a stretch target: this
# module was run against the tree at commit 8c3d801 with all six
# comment tickets landed and Part A of ticket 008 applied (Part A edits
# `src/DESIGN.md`, which no suffix in `_SOURCE_SUFFIXES` matches, so it
# moves neither ratchet). The cleanup was concentrated: ticket 005's
# pass over the four `comms/wire_*` files alone took those files
# 173 -> 63 markers and the repo-wide total 292 -> 182.
#
# The four files still carrying the bulk are `src/shims.cpp` (33),
# `comms/wire_handler.cpp` (24), `motion/motion_engine.h` (24) and
# `comms/wire_handler.h` (22) -- 103 of the 173. What remains in them
# is dominated by live spec citations (`protocol.md`, `motion-api.md`,
# `src/DESIGN.md`), which this regex deliberately does not try to tell
# apart from archaeology (see the module docstring), so 173 is NOT a
# floor to drive to zero. Ratchets DOWN only from here.
_BUDGET = 173

# Comment-volume baselines, one per project-owned `src/` source file.
#
# RE-SEEDED 2026-09-06 (sprint 035 ticket 008) from the post-cleanup
# tree at commit 8c3d801, applying the counting rule in the module
# docstring to every `src/**/*.{h,cpp,ts}` outside `_EXCLUDED`. There is
# no hardware in this measurement -- it reads files as text. Same 46
# files as the seed; none was added or removed by this sprint, and none
# is missing a baseline (`test_comment_volume_ratio_is_within_per_file_baseline`
# reports unbaselined files, and reported none).
#
# The seed came from the pre-cleanup tree at commit df596f8 (sprint 035
# ticket 001) and its aggregate was 7866 comment / 6987 code = 1.126.
# Tickets 002-006 then cut comments in 30 of these files, WITHOUT
# touching a line of code: the aggregate is now 6585 / 6987 = 0.943,
# and every one of the 6987 code-line counts is byte-identical to the
# seed's. See `clasi/sprints/035-.../sprint.md`'s "Verification pass"
# table for the per-file baseline-vs-achieved delta.
#
# Every entry below is the ACHIEVED value, rounded to two decimals.
# No stretch target was invented and no file was given headroom: a
# baseline set below what the tree actually achieves fails the next
# unrelated sprint for no reason, and one set above it silently gives
# back ground this sprint paid for. The consequence is that several
# files now sit within a comment line or two of their ceiling
# (`core/encoder_glitch_armor.h`, `motion/segment.h`, `blocks/motion.ts`
# are the tightest, each under `_RATIO_TOLERANCE`'s slack) -- which is
# the ratchet working as designed. Adding a load-bearing comment to one
# of them is a reviewed raise of that entry, per the failure message.
#
# Sorted by ratio, descending, matching the sprint.md table. Ratchets
# DOWN only -- raising an entry is its own reviewed edit.
_RATIO_BASELINE = {
    "src/core/fiber_identity.h": 4.00,  # 28 / 7
    "src/comms/serial_transport.h": 3.89,  # 70 / 18
    "src/comms/wire_adapter.h": 3.74,  # 262 / 70
    "src/motion/motion_engine.h": 3.70,  # 396 / 107
    "src/comms/radio_transport.h": 3.69,  # 258 / 70
    "src/comms/protocol.h": 3.58,  # 351 / 98
    "src/core/motion_owner.h": 3.56,  # 64 / 18
    "src/platform/vfp_guard.h": 3.54,  # 46 / 13
    "src/core/heading_wrap.h": 2.82,  # 31 / 11
    "src/core/bus_guard.h": 2.67,  # 48 / 18
    "src/core/encoder_glitch_armor.h": 2.45,  # 108 / 44
    "src/comms/run_bridge.h": 2.32,  # 79 / 34
    "src/comms/wire_handler.h": 2.07,  # 455 / 220
    "src/comms/transport_sink.h": 1.92,  # 46 / 24
    "src/motion/velocity_shaper.h": 1.90,  # 38 / 20
    "src/comms/config_fields.h": 1.61,  # 95 / 59
    "src/comms/wifi_uart.h": 1.58,  # 30 / 19
    "src/shims.cpp": 1.42,  # 1007 / 710
    "src/motion/segment.h": 1.38,  # 90 / 65
    "src/motion/odometry.h": 1.33,  # 76 / 57
    "src/motion/motion_limits.h": 1.26,  # 73 / 58
    "src/motion/velocity_shaper.cpp": 1.20,  # 65 / 54
    "src/comms/wire_adapter.cpp": 1.19,  # 474 / 397
    "src/comms/protocol.cpp": 1.15,  # 389 / 338
    "src/comms/serial_transport.cpp": 0.83,  # 43 / 52
    "src/comms/emit_queue.h": 0.80,  # 39 / 49
    "src/platform/nezha_port.h": 0.78,  # 58 / 74
    "src/platform/otos_port.h": 0.75,  # 52 / 69
    "src/platform/nezha_port.cpp": 0.74,  # 189 / 255
    "src/platform/platform_ports.h": 0.74,  # 20 / 27
    "src/motion/motion_engine.cpp": 0.73,  # 218 / 299
    "src/comms/wire_handler.cpp": 0.68,  # 565 / 834
    "src/comms/wifi_link.h": 0.64,  # 145 / 226
    "src/comms/run_queue.h": 0.59,  # 36 / 61
    "src/platform/vfp_guard.cpp": 0.58,  # 7 / 12
    "src/comms/radio_transport.cpp": 0.57,  # 64 / 112
    "src/comms/run_bridge.cpp": 0.56,  # 34 / 61
    "src/blocks/world.ts": 0.45,  # 71 / 157
    "src/blocks/sim.ts": 0.44,  # 165 / 379
    "src/comms/wifi_uart.cpp": 0.35,  # 11 / 31
    "src/platform/otos_port.cpp": 0.27,  # 44 / 163
    "src/blocks/run.ts": 0.23,  # 56 / 243
    "src/blocks/motion.ts": 0.17,  # 74 / 423
    "src/comms/wifi_link.cpp": 0.13,  # 113 / 844
    "src/blocks/pose.ts": 0.03,  # 1 / 38
    "src/blocks/stop.ts": 0.02,  # 1 / 49
}

# The baselines above are recorded to two decimals so they can be read
# against the sprint.md table by eye. Rounding to two decimals rounds
# DOWN as often as up -- 25 of the 46 files sit fractionally above their
# printed baseline the moment they are seeded (`src/blocks/motion.ts` is
# 0.174941, printed 0.17) -- so a strict comparison against the printed
# value would fail on the very tree it was measured from. Compare with
# half of the last printed digit instead. The slack this buys an author
# is bounded by the file's size: 0.005 is under one comment line in
# every file here but the largest, and about four lines in
# `comms/wire_handler.cpp` (834 code lines), well inside the drift this
# ratchet exists to catch.
_RATIO_TOLERANCE = 0.005


def _count_comment_and_code(text):
    """Split `text` into (comment lines, code lines) under the counting
    rule documented in the module docstring: a line stripped of leading
    whitespace that begins with `//` but not `//%` is a comment; every
    other non-blank line is code; blank lines are neither."""
    comment = 0
    code = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped:
            continue
        if stripped.startswith("//") and not stripped.startswith("//%"):
            comment += 1
        else:
            code += 1
    return comment, code


def _comment_ratio_by_file():
    """Map repo-relative path -> (comment lines, code lines, ratio) for
    every project-owned `src/` source file. Same file set as
    `_marker_line_count()`: `_SOURCE_SUFFIXES`, minus `_EXCLUDED`."""
    ratios = {}
    for p in sorted(_SRC_DIR.rglob("*")):
        if not p.is_file() or p.suffix not in _SOURCE_SUFFIXES or p in _EXCLUDED:
            continue
        comment, code = _count_comment_and_code(p.read_text(errors="ignore"))
        if code == 0:
            continue
        ratios[p.relative_to(_REPO_ROOT).as_posix()] = (comment, code, comment / code)
    return ratios


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


# A hand-counted fixture for the counting rule itself. Every baseline in
# `_RATIO_BASELINE` is derived from this rule, so a future edit to
# `_count_comment_and_code()` would silently reshuffle all 46 of them
# rather than failing. This pins the rule so such an edit fails loudly,
# right where the reason for each exclusion is written down.
#
# Expected: 2 comment lines, 6 code lines, 1 blank counted as neither.
_COUNTING_RULE_FIXTURE = """\
// A plain comment line -- COMMENT.
//% block="drive %distance cm" group="Motion"
        //   An indented comment, still a COMMENT.
    float velocity = 0.0f;  // [mm/s] -- CODE; the trailing unit comment

/**
 * Student-facing JSDoc PXT renders into the toolbox -- CODE, all three
 */
    void advance(float target, float dt);
"""


def test_comment_counting_rule_matches_its_specification():
    """The counting rule handles `//`, `//%`, an indented `//`, a
    trailing `// [unit]`, a `/** */` JSDoc block and a blank line
    exactly as the module docstring says it does. See
    `_COUNTING_RULE_FIXTURE` for the line-by-line expectation."""
    comment, code = _count_comment_and_code(_COUNTING_RULE_FIXTURE)
    assert (comment, code) == (2, 6), (
        "the comment/code counting rule changed: expected 2 comment and 6 "
        f"code lines from the fixture, got {comment} and {code}. Every "
        "value in _RATIO_BASELINE was measured under the documented rule, "
        "so changing the rule invalidates all of them -- re-measure and "
        "re-seed the whole dict, do not patch this expectation."
    )
    # Guard the three documented exclusions individually, so a failure
    # names which one broke rather than only that the totals moved.
    assert _count_comment_and_code('//% block="x"\n') == (0, 1)
    assert _count_comment_and_code("int x = 1;  // [mm]\n") == (0, 1)
    assert _count_comment_and_code("/** doc */\n") == (0, 1)
    assert _count_comment_and_code("  // plain\n") == (1, 0)
    assert _count_comment_and_code("\n   \n") == (0, 0)


def test_comment_volume_ratio_is_within_per_file_baseline():
    """Comment lines per code line, per project-owned `src/` file, must
    not exceed that file's recorded baseline. This is the second,
    independent ratchet: `test_archaeology_marker_count_is_within_budget`
    catches archaeology, this one catches length, and they are kept
    separate on purpose (see the module docstring). A file with no
    baseline entry is reported, never failed."""
    ratios = _comment_ratio_by_file()

    regressions = []
    for path, baseline in sorted(_RATIO_BASELINE.items()):
        measured = ratios.get(path)
        if measured is None:
            # Deleted or renamed since the baseline was taken. Not a
            # comment regression; the stale entry is cleaned up when the
            # dict is next re-seeded.
            continue
        comment, code, ratio = measured
        if ratio > baseline + _RATIO_TOLERANCE:
            regressions.append(
                f"  {path}: baseline {baseline:.2f}, now {ratio:.2f} "
                f"({comment} comment / {code} code lines)"
            )

    unbaselined = sorted(set(ratios) - set(_RATIO_BASELINE))
    note = ""
    if unbaselined:
        note = (
            "\n\nNote (not a failure): these project-owned src/ files have no "
            "_RATIO_BASELINE entry, so they are unratcheted -- add them when "
            f"the dict is next re-seeded: {unbaselined}"
        )

    assert not regressions, (
        "comment volume regressed past its per-file baseline "
        "(comment lines / code lines, counting rule in this module's "
        "docstring):\n" + "\n".join(regressions) + "\n\nTwo legitimate "
        "responses, and only two: (1) cut the comment -- state the "
        "current contract and delete the archaeology, per "
        "`docs/code-review/guidelines.md`'s write-time standard and its "
        "recurring anti-patterns; or (2) raise this file's "
        "_RATIO_BASELINE entry as its own explicit, reviewed edit, "
        "because the added lines are load-bearing (a contract, a unit, a "
        "measured fact with its artifact). What is NOT a response is "
        "raising the baseline incidentally along with the change that "
        "moved it -- this ratchet only ratchets down." + note
    )
