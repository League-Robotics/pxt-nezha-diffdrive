"""tests/host/test_segment_lazy_origin.py -- design docs/design/
motion-profile-unification.md S9.4: "a rebasePosition() requested
between start() and the first service() does not change the segment's
measured progress."

Segment's lazy origin capture (segment.h's own header comment, design
S6.5) exists precisely to retire the old MoveState's own
positionEpochLeft0/Right0 pair -- a guard the pre-ticket-003 engine
needed because it captured its origin SYNCHRONOUSLY at startSegment()
time, which could be BEFORE a rebase the caller had already requested
landed on the kernel's own next step(). A Segment never drives anything
at construction (moveX()/wheelsX() only arm state); its origin is
captured on the FIRST MotionEngine::service() call, which always runs
AFTER that tick's own kernel_.step() -- so any rebasePosition() request
made between start() and that first service() has ALREADY been applied,
by the same step(), before the origin capture ever reads
Output.positionLeft/Right (motion_engine.cpp: "the caller's own step()
has already run, and applied any deferred rebase, before service() is
ever called").

Proof strategy: run the SAME moveX() twice from the SAME nonzero
starting wheel position (500 counts on each side, simulating a robot
that has already travelled before this move begins) -- once with a
kernel.rebasePosition() request issued between moveX() and the first
service() call, once without -- and drive both through to completion
with the identical scripted encoder trajectory. If the segment's origin
capture were reading STALE positions (captured before a pending rebase
landed, the defect the old positionEpochLeft0/Right0 pair had to guard
against), the two runs would diverge: the rebased run's very first
`remaining()`/`progress()` reading would be offset by the 500-count
head start instead of starting fresh. They must instead be identical,
tick for tick.

Run with::

    uv run pytest tests/host/test_segment_lazy_origin.py
"""

import ctypes

from test_motion_engine_reductions import (  # noqa: F401 -- motion_lib re-exported as a fixture
    LEFT,
    RIGHT,
    Engine,
    _ready,
    motion_lib,
)

_START_POSITION_COUNTS = 500.0  # [counts] simulates prior wheel travel


def _bind_rebase(lib):
    lib.meRebasePosition.argtypes = [ctypes.c_void_p]
    lib.meRebasePosition.restype = None
    return lib


def _run_pivot_from_nonzero_start(motion_lib, rebase_before_first_service):
    """Arms both wheels at `_START_POSITION_COUNTS` (a robot that has
    already travelled before this move starts), issues a 90 deg pivot,
    optionally requests a kernel rebase between start() and the first
    service() call, then drives the segment to completion via a
    scripted, DETERMINISTIC encoder trajectory (independent of
    `rebase_before_first_service` -- both runs see the identical
    absolute position sequence, so any difference in the returned
    progress trace can only come from the segment's own origin
    handling, never from a different simulated trajectory). Returns the
    list of `engine.progress()` readings, one per tick."""
    lib = _bind_rebase(motion_lib)
    with Engine(motion_lib) as e:
        _ready(e)
        cpm = e.counts_per_mm()
        b = e.effective_track_width()

        e.set_clock(0)
        e.arm_motor_position_at(LEFT, _START_POSITION_COUNTS, 1)
        e.arm_motor_position_at(RIGHT, _START_POSITION_COUNTS, 2)
        e.step()  # lands the pre-existing 500-count position in Output

        e.move_x(0.0, 1.5707963267948966, 100.0, 30000)  # start(): pi/2
        if rebase_before_first_service:
            lib.meRebasePosition(e._handle)

        yaw_target = 1.5707963267948966 * 0.5 * b * cpm
        # A deterministic 5-step ramp from 0 to the full yaw target,
        # relative to the SAME `_START_POSITION_COUNTS` absolute base
        # both runs share -- identical script either way.
        progress_trace = []
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            diff = frac * yaw_target
            e.arm_motor_position_at(
                LEFT, _START_POSITION_COUNTS - diff, 100 + int(frac * 10))
            e.arm_motor_position_at(
                RIGHT, _START_POSITION_COUNTS + diff, 200 + int(frac * 10))
            e.set_clock(24_000 * (len(progress_trace) + 1))
            e.step()
            e.service_move()
            progress_trace.append(e.progress())
        return progress_trace


def test_rebase_between_start_and_first_service_does_not_change_progress(
        motion_lib):
    without_rebase = _run_pivot_from_nonzero_start(
        motion_lib, rebase_before_first_service=False)
    with_rebase = _run_pivot_from_nonzero_start(
        motion_lib, rebase_before_first_service=True)

    assert with_rebase == without_rebase, (
        "a kernel.rebasePosition() requested between moveX() and the "
        "segment's own first service() call changed its measured "
        f"progress: without rebase {without_rebase}, with rebase "
        f"{with_rebase}. Segment::posLeft0/posRight0 (segment.h) must "
        "be captured strictly AFTER the tick that applies any pending "
        "rebase (design S6.5) -- if this diverges, the origin capture "
        "has gone stale the same way the old MoveState's own "
        "positionEpochLeft0/Right0 pair had to guard against."
    )
    # Sanity: the trace is a real, monotonically-progressing pivot, not
    # a degenerate all-zero or all-1000 readout that would make the
    # equality above vacuous.
    assert without_rebase[0] < without_rebase[-1]
    assert without_rebase[-1] >= 999  # essentially complete by the last step


def test_rebase_does_not_leak_the_pre_existing_position_into_progress(
        motion_lib):
    """A stronger form of the same claim: the FIRST progress reading
    after a rebase must be close to what a segment starting from a
    genuine zero position would report -- not offset by the 500-count
    head start the rebase was supposed to erase. (The equality test
    above already proves this indirectly by matching the no-rebase
    run; this test pins the concrete expected shape instead of only a
    relative comparison.)"""
    with_rebase = _run_pivot_from_nonzero_start(
        motion_lib, rebase_before_first_service=True)
    # First reading is frac=0.0 (no yaw progress armed yet beyond the
    # origin tick itself) -- must read as "just started", not pinned to
    # 1000 (which a stale, already-nonzero origin baseline could
    # produce if the 500-count head start were mistaken for progress).
    assert with_rebase[0] < 100, (
        f"first progress reading after a rebase was {with_rebase[0]}, "
        "expected close to 0 -- the pre-existing 500-count wheel "
        "position must not leak into the segment's own progress "
        "baseline"
    )
