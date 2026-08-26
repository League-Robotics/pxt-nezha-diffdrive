"""tests/host/test_wire_motion_completion.py -- sprint 005 ticket 004
(closing wire-motion-completion-signal.md/R-23): src/comms/wire_adapter.h's
real lastDone()/lastDoneReason(), previously permanently inert
(0/kNone) since sprint 003 ticket 012 -- see that file's own header
comment for the full design this ticket implements.

Reuses test_wire_motion_verbs.py's `wa`/`motion_verb_lib` fixtures (the
REAL WireAdapter + a REAL DiffDrive kernel + a REAL MotionEngine over
FakeMotor) rather than a new shim, same "one shim, several pytest
files" pattern test_wire_reliability.py already uses against
test_wire_grammar.py's own fixtures. Every test here drives the REAL
adapter, not WireMockAdapter -- that mock's own lastDone()/
lastDoneReason() fields are untouched by this ticket (see
wire_mock_adapter.h) and are not exercised here.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++): radio-robot-lib/docs/design/
protocol.md S8.8 (the completion channel: polled fresh off the Adapter
on every ack/nack, never cached on WireHandler).

Five terminal reasons (sprint.md SUC-006):
  - kStop     -- the motion reached its own stop condition, or an
                 explicit STOP ended it.
  - kAborted  -- a later motion verb superseded a still-live one
                 ("superseded").
  - kTimeout  -- a lease-style verb's deadline elapsed with nothing
                 superseding it, or a goal-directed move's deadline
                 elapsed before it reached its own goal.
  - kStall    -- the kernel's REAL stall latch halted the drivetrain
                 during a move.
  - kEstop    -- a REAL ESTOP landed during a move.

Run with::

    uv run pytest tests/host/test_wire_motion_completion.py
"""

import pytest

from test_wire_motion_verbs import (  # noqa: F401 -- wa re-exported as a fixture
    DONE_ABORTED,
    DONE_ESTOP,
    DONE_NONE,
    DONE_STALL,
    DONE_STOP,
    DONE_TIMEOUT,
    LEFT,
    RIGHT,
    STATUS_OK,
    _ack,
    motion_verb_lib,
    wa,
)


def _ready(wa, max_duty=100.0, full_duty_velocity=1000.0):
    wa.set_max_duty(max_duty)
    wa.set_full_duty_velocity(full_duty_velocity)
    assert wa.begin() == STATUS_OK


# ---------------------------------------------------------------------------
# Pre-completion default (AC): before any motion verb has ever completed,
# lastDone() reports 0 and lastDoneReason() reports kNone -- the
# pre-existing "nothing completed yet" case this ticket's new bookkeeping
# must not break.
# ---------------------------------------------------------------------------


def test_pre_completion_default_is_zero_and_none(wa):
    _ready(wa)
    assert wa.last_done() == 0
    assert wa.last_done_reason() == DONE_NONE

    # Still the default after a verb that ISN'T a motion verb -- GET/SET/
    # STATUS/etc. never touch the completion channel at all.
    wa.feed(b"STATUS #1\n")
    wa.take_sink()
    assert wa.last_done() == 0
    assert wa.last_done_reason() == DONE_NONE


# ---------------------------------------------------------------------------
# kTimeout: a lease-style verb's deadline elapses with nothing
# superseding it (SUC-006 main flow item 3).
# ---------------------------------------------------------------------------


def test_wheels_v_lease_elapses_with_nothing_superseding_reports_timeout(wa):
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 1000 #1\n")
    assert wa.take_sink() == _ack(1)
    # Not yet resolved -- the lease (deadline 1000+1000=2000) has not
    # elapsed.
    assert wa.last_done_reason() == DONE_NONE

    wa.set_now_ms(2001)  # past the deadline
    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_TIMEOUT

    # Frozen: a further read (S8.8 "read fresh," not "recompute forever")
    # still reports the same committed pair.
    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_TIMEOUT


def test_wheels_v_natural_timeout_then_poll_clears_the_obligation_flag(wa):
    """sprint 016 ticket 003 (closing wire-motion-obligation-never-clears.md):
    resolvePendingIfDue() must clear the underlying motionObligationActive_
    flag itself when it commits a resolution, not just rely on
    hasLiveMotionObligation()'s own time gate to mask a flag left armed
    forever.

    For a LEASE-STYLE verb like WHEELS_V, natural completion coincides
    exactly with the lease deadline elapsing, so hasLiveMotionObligation()
    already reads false the instant `now` passes that deadline -- with or
    without this ticket's fix, since its time check dominates whenever
    `now` is at or past the deadline. The pre-fix bug is that the
    INTERNAL flag itself stays armed forever after that (only an explicit
    STOP/ESTOP ever cleared it) -- latent, but real: hasLiveMotionObligation()
    does `motionObligationActive_ && (now - deadline) < 0`
    (wire_adapter.cpp's own wraparound-safe signed-difference idiom), so
    setting the clock back to a value that is again "before" the stale
    deadline -- the same numeric effect a real millis() wraparound
    eventually produces on an uptime long enough to matter -- makes it
    read true again pre-fix. Post-fix, resolvePendingIfDue()'s own commit
    (triggered by last_done_reason() below) already cleared the flag, so
    it reads false regardless of what the clock does afterward.
    """
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 1000 #1\n")  # deadline 2000
    assert wa.take_sink() == _ack(1)

    wa.set_now_ms(2001)  # past the deadline -- naturally timed out
    assert wa.last_done_reason() == DONE_TIMEOUT  # polls resolvePendingIfDue()

    # Jump the clock back inside the ORIGINAL lease window (1000..2000).
    wa.set_now_ms(1500)
    assert not wa.has_live_motion_obligation()


def test_move_x_deadline_elapses_before_reaching_goal_reports_timeout(wa):
    """GOAL-DIRECTED verb, the OTHER half of kTimeout: MOVE_X's own
    deadline elapses while MotionEngine's move-engine state is STILL
    active (the move never reached distDone/yawDone) -- distinguished
    from kStop via engineMoveActive() (this ticket's one genuinely new
    read), not the wire-side deadline alone."""
    _ready(wa)
    wa.set_now_ms(1000)

    # A big distance and a short timeout: the move cannot possibly reach
    # its own goal before the deadline backstop fires.
    wa.feed(b"MOVE_X 5000 0 50 500 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    # Advance past the deadline (1000+500=1500) WITHOUT arming any
    # encoder progress -- the move never gets anywhere near distDone.
    wa.set_now_ms(1600)
    still_active = wa.service_move()  # MotionEngine's own deadline check
    assert not still_active
    assert not wa.engine_move_active()

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_TIMEOUT


# ---------------------------------------------------------------------------
# kStop: the motion reaches its own stop condition (SUC-006 main flow
# item 1), or an explicit STOP ends it early (Wire::DoneReason::kStop's
# own doc comment, wire_handler.h).
# ---------------------------------------------------------------------------


def test_move_x_reaching_its_own_goal_early_reports_stop(wa):
    """GOAL-DIRECTED verb: the move reaches distDone/yawDone (a REAL
    encoder position, armed via FakeMotor) well before its own generous
    deadline -- distinguished from kTimeout by engineMoveActive() going
    false while hasLiveMotionObligation() is STILL true."""
    _ready(wa)
    wa.set_now_ms(1000)
    cpm = wa.counts_per_mm()

    # Straight line (rotation=0): distTarget == distance * cpm, both
    # wheels' target is identical (motion-api.md S2's wheels_x
    # reduction: left = distTarget - yawTarget, right = distTarget +
    # yawTarget, and yawTarget is 0 here).
    distance_mm = 200.0
    dist_target_counts = distance_mm * cpm
    wa.feed(b"MOVE_X 200 0 150 5000 #1\n")  # generous 5000ms timeout
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()
    # Not yet resolved -- no progress armed yet.
    assert wa.last_done_reason() == DONE_NONE

    # Simulate "the wheels have physically reached the target" -- direct
    # position arming (fake_ports.h's own contract), not a hand-rolled
    # duty-to-position physics model.
    wa.arm_motor_position(LEFT, dist_target_counts, sample_time_us=1)
    wa.arm_motor_position(RIGHT, dist_target_counts, sample_time_us=1)
    wa.step()  # commits the armed position into Output.positionLeft/Right
    still_active = wa.service_move()  # MotionEngine's own distDone check
    assert not still_active
    assert not wa.engine_move_active()

    # Nowhere near the 5000ms deadline (now is still ~1000-1050ms) --
    # this is a REAL early completion, not a coincidental deadline hit.
    assert wa.has_live_motion_obligation()
    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_STOP


def test_move_x_reaching_its_own_goal_early_then_poll_clears_the_obligation_flag(wa):
    """sprint 016 ticket 003 (closing wire-motion-obligation-never-clears.md):
    the GOAL-DIRECTED counterpart of
    test_wheels_v_natural_timeout_then_poll_clears_the_obligation_flag
    above, and the scenario this ticket actually exists for -- unlike a
    lease-style verb, a goal-directed move can reach its own goal LONG
    before its declared `timeout`. Pre-fix, motionObligationActive_ stayed
    armed until that full declared timeout elapsed (or an explicit
    STOP/ESTOP) even though the move had already finished -- so
    protocol.cpp's fiber loop (`hasLiveMotionObligation()` is its own tick
    gate, protocol.cpp:355) kept ticking the kernel at 24 ms for the rest
    of that window for no reason. Post-fix, polling last_done_reason()
    (which observes the early kStop via engineMoveActive() going false)
    also clears the obligation immediately, well before the 5000ms
    deadline -- no clock trickery needed here, unlike the lease-style
    test above, because this early-completion gap is directly observable
    with `now` never advancing past the real deadline at all."""
    _ready(wa)
    wa.set_now_ms(1000)
    cpm = wa.counts_per_mm()

    distance_mm = 200.0
    dist_target_counts = distance_mm * cpm
    wa.feed(b"MOVE_X 200 0 150 5000 #1\n")  # generous 5000ms timeout
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    wa.arm_motor_position(LEFT, dist_target_counts, sample_time_us=1)
    wa.arm_motor_position(RIGHT, dist_target_counts, sample_time_us=1)
    wa.step()
    still_active = wa.service_move()
    assert not still_active
    assert not wa.engine_move_active()

    # Nowhere near the 5000ms deadline (now is still ~1000-1050ms).
    assert wa.has_live_motion_obligation()
    assert wa.last_done_reason() == DONE_STOP  # polls resolvePendingIfDue()

    # The declared timeout has NOT elapsed -- pre-fix, the internal flag
    # stayed armed regardless, so hasLiveMotionObligation()'s time gate
    # alone would still read true here. Post-fix, resolvePendingIfDue()'s
    # own commit (triggered by last_done_reason() just above) already
    # cleared it.
    assert not wa.has_live_motion_obligation()


def test_explicit_stop_ends_a_pending_lease_style_motion_as_stop(wa):
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)

    # STOP's own ack is formatted BEFORE onStop() runs (dispatch() replies
    # ack, then executes) -- so it still reports the pre-resolution
    # default, exactly like every ack before this ticket.
    wa.feed(b"STOP #2\n")
    assert wa.take_sink() == _ack(2)

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_STOP


def test_explicit_stop_ends_a_pending_goal_directed_motion_as_stop(wa):
    """STOP's own stopAll() force-ends the move-engine (engine.endMove())
    -- engineMoveActive() reads false immediately, and since the wire-side
    deadline has not elapsed, resolvePendingReason() naturally resolves
    this to kStop (the same reason a real early completion produces),
    not kTimeout."""
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"MOVE_X 500 0 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    wa.feed(b"STOP #2\n")
    assert wa.take_sink() == _ack(2)
    assert not wa.engine_move_active()

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_STOP


# ---------------------------------------------------------------------------
# kAborted ("superseded"): a later motion verb replacing a still-live one
# (SUC-006 main flow item 2). Covers both directions of the ordering
# hazard this ticket's own implementation found: a LEASE-STYLE verb's own
# dispatch (setWheelsTimed()/engineWheelsX()/engineMoveV(), all of which
# route through MotionEngine::wheelsV()/wheelsX(), whose FIRST act is
# cancelMove()) must not be misread as the superseded motion having
# reached its own stop condition.
# ---------------------------------------------------------------------------


def test_second_wheels_v_supersedes_first_still_live_one_as_aborted(wa):
    """The exact scenario sprint.md's own SUC-006 acceptance criteria
    calls out by name: 'an in-flight WHEELS_V superseded by a new
    WHEELS_V before its lease expires reports kAborted, not kTimeout.'"""
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)

    # #2's own ack is formatted BEFORE onWheelsV() runs -- still the
    # pre-resolution default, same as every ack before this ticket.
    wa.feed(b"WHEELS_V 50 50 5000 #2\n")
    assert wa.take_sink() == _ack(2)

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_ABORTED


def test_wheels_v_supersedes_a_still_live_move_x_as_aborted_not_stop(wa):
    """Regression test for the ordering hazard found while implementing
    this ticket: WHEELS_V's own dispatch (setWheelsTimed() ->
    MotionEngine::wheelsV()) calls cancelMove() FIRST (motion-api.md S6:
    'wheels_* clears the planner'), which -- if this class's own
    supersede resolution ran AFTER that dispatch instead of before --
    would make the superseded MOVE_X's engineMoveActive() already read
    false, and resolvePendingReason() would misclassify it as having
    reached its own stop condition (kStop) instead of having been
    superseded (kAborted). WireAdapter resolves the OLD pending BEFORE
    calling into MotionEngine for exactly this reason."""
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"MOVE_X 500 0 100 4000 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    wa.feed(b"WHEELS_V 100 100 500 #2\n")
    assert wa.take_sink() == _ack(2)
    assert not wa.engine_move_active()  # cancelMove() ran, as expected

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_ABORTED  # NOT kStop


def test_move_x_supersedes_a_still_live_wheels_v_as_aborted(wa):
    """The other direction: a GOAL-DIRECTED verb superseding a still-live
    LEASE-STYLE one. engineMoveX() does not clear a lease-style pending's
    own state (only cancelMove()-calling primitives do), so this exercises
    the plain deadline-based resolution path -- included for completeness
    alongside the WHEELS_V-supersedes-MOVE_X direction above."""
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)

    wa.feed(b"MOVE_X 200 0 100 4000 #2\n")
    assert wa.take_sink() == _ack(2)

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_ABORTED


# ---------------------------------------------------------------------------
# kStall: the kernel's REAL stall latch halts the drivetrain during a
# move (SUC-006 main flow item 4) -- driven the same way
# test_wire_motion_verbs.py's own
# test_stall_clear_wire_field_clears_latch_and_reads_back proves the
# latch itself (sustained demand + still encoders past the configured
# window), not a diagValue() override shortcut.
# ---------------------------------------------------------------------------


def test_stall_latch_during_a_move_reports_stall(wa):
    _ready(wa)

    wa.feed(b"SET stall_speed 50 #1\n")
    assert wa.take_sink() == _ack(1)
    wa.feed(b"SET stall_demand 200 #2\n")
    assert wa.take_sink() == _ack(2)
    wa.feed(b"SET stall_window 500 #3\n")
    assert wa.take_sink() == _ack(3)

    wa.set_now_ms(1000)  # never 0 -- updateLatch()'s own `since == 0`
                         # sentinel (test_kernel_harness.py)
    wa.step()  # priming step -- see test_stall_clear's own comment
               # (test_wire_motion_verbs.py) for why this is needed

    wa.feed(b"WHEELS_V 500 500 5000 #4\n")
    assert wa.take_sink() == _ack(4)
    assert wa.last_done_reason() == DONE_NONE  # not yet resolved

    wa.step()  # first "demanding && still" observation, since=1000ms
    wa.set_now_ms(1600)  # +600ms > stall_window -> latches this step()
    wa.step()

    assert wa.last_done() == 4
    assert wa.last_done_reason() == DONE_STALL


# ---------------------------------------------------------------------------
# kEstop: a REAL ESTOP lands during a move (SUC-006 main flow item 5).
# ---------------------------------------------------------------------------


def test_estop_during_a_lease_style_motion_reports_estop(wa):
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)

    wa.feed(b"ESTOP\n")
    assert wa.take_sink() == b"estop\n"

    # Resolved immediately by onEstop() itself, with no step() needed --
    # unlike diagValue(kDiagEstopped) (a published Output field that only
    # updates on the kernel's NEXT step()), this class's own completion
    # channel does not wait for that publish.
    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_ESTOP


def test_estop_during_a_goal_directed_motion_reports_estop_not_stop(wa):
    """Regression test for the staleness hazard found while implementing
    this ticket: estopAll() force-ends any in-flight goal-directed move
    (engine.endMove()) SYNCHRONOUSLY, the same way a real early
    completion would -- and diagValue(kDiagEstopped) has not been
    published yet at this exact instant (that only happens on the
    kernel's NEXT step()). A naive 'trust the natural resolution first'
    commit would misread this combination as kStop. onEstop() commits
    kEstop unconditionally for exactly this reason."""
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"MOVE_X 500 0 100 5000 #1\n")
    assert wa.take_sink() == _ack(1)
    assert wa.engine_move_active()

    wa.feed(b"ESTOP\n")
    assert wa.take_sink() == b"estop\n"
    assert not wa.engine_move_active()  # engine.endMove() ran

    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_ESTOP  # NOT kStop


# ---------------------------------------------------------------------------
# S8.8: lastDone()/lastDoneReason() are read FRESH on every call -- no
# cached copy -- against the REAL WireAdapter (test_wire_reliability.py's
# test_last_done_is_read_fresh_not_cached_across_calls proves the
# identical contract against WireMockAdapter; this is that pattern's
# real-adapter equivalent, driven through actual state changes rather
# than a settable mock field).
# ---------------------------------------------------------------------------


def test_last_done_is_read_fresh_not_cached_across_calls(wa):
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 1000 #1\n")  # deadline 2000
    assert wa.take_sink() == _ack(1)
    assert wa.last_done() == 0
    assert wa.last_done_reason() == DONE_NONE

    wa.set_now_ms(2001)  # #1's lease elapses
    assert wa.last_done() == 1
    assert wa.last_done_reason() == DONE_TIMEOUT

    # A SECOND motion verb resolves to a DIFFERENT terminal reason --
    # proving each read reflects current state, not a value latched the
    # first time lastDone()/lastDoneReason() were ever called. #2's own
    # ack still carries #1's already-committed (1, timeout) -- it was
    # resolved (and frozen) by the direct poll above, before #2 was ever
    # accepted, so there is nothing left pending for #2's own dispatch to
    # supersede.
    wa.set_now_ms(3000)
    wa.feed(b"WHEELS_V 50 50 5000 #2\n")  # a fresh, generous lease
    assert wa.take_sink() == _ack(2, 1, DONE_TIMEOUT)
    # #3's own ack STILL carries #1's pair -- #2 is not yet resolved at
    # ack(3) time either (ack sent before onStop() runs).
    wa.feed(b"STOP #3\n")
    assert wa.take_sink() == _ack(3, 1, DONE_TIMEOUT)
    assert wa.last_done() == 2
    assert wa.last_done_reason() == DONE_STOP


# ---------------------------------------------------------------------------
# The ack/nack wire surface itself: a host observes the completion
# channel through a SUBSEQUENT sequenced verb's own ack, not only through
# the direct waLastDone()/waLastDoneReason() accessors used above --
# proving the production reading path (WireHandler::replyAck/replyNack
# polling adapter_.lastDone()/lastDoneReason()) carries the same values.
# ---------------------------------------------------------------------------


def test_ack_of_a_later_verb_carries_the_resolved_completion(wa):
    _ready(wa)
    wa.set_now_ms(1000)

    wa.feed(b"WHEELS_V 100 100 1000 #1\n")
    assert wa.take_sink() == _ack(1)

    wa.set_now_ms(2001)
    wa.feed(b"STATUS #2\n")
    reply = wa.take_sink()
    assert reply.startswith(_ack(2, 1, DONE_TIMEOUT))


# ---------------------------------------------------------------------------
# sprint 016 ticket 004 (re-checking i2c-fault-count-climbs-on-idle-bus.md
# against ticket 003's obligation-clearing fix): quantifies exactly what
# ticket 003 changed, for a representative wide-timeout goal-directed verb
# that reaches its own goal almost immediately. See this ticket's own
# Findings section and clasi/issues/i2c-fault-count-climbs-on-idle-bus.md
# for the full verdict -- this test establishes the HOST-provable half of
# it only: the mechanical precondition (how long the obligation window
# stays open), not the I2C fault count itself (no I2C exists on the host).
# ---------------------------------------------------------------------------


def test_obligation_window_narrows_after_natural_completion(wa):
    """protocol.cpp's fiber loop (protocol.cpp:350-357) calls tickDrive()
    back-to-back with NO sleep whenever hasLiveMotionObligation() is true,
    gated only by tickDrive()'s own ~24 ms self-paced kernel.step() cadence
    (shims.cpp's own documented figure, restated independently in
    DESIGN.md/encoder_glitch_armor.h/nezha_port.h/serial_transport.h) --
    so the obligation window's duration converts directly into a
    tickDrive()/kernel.step() count, and kernel.step() is the ONLY place
    `cyc` (diagValue(16), telemetry's own `cyc` column) advances
    (shims.cpp: kernel.step() is called nowhere outside tickDrive()).

    BEFORE ticket 003 (verified directly against the pre-fix
    wire_adapter.cpp via `git stash`, recorded in ticket 003's own
    Findings): hasLiveMotionObligation() stays true for the ENTIRE
    declared timeout regardless of when the move actually finishes, or
    until an explicit STOP/ESTOP -- polling lastDone()/lastDoneReason() in
    between changes nothing pre-fix, because resolvePendingIfDue()/
    forceResolvePending() never touched motionObligationActive_ then.

    AFTER ticket 003 (asserted here, against the current, fixed code): the
    window closes as soon as something next polls
    lastDone()/lastDoneReason() following the real completion -- which in
    production only happens via WireHandler::replyAck()/replyNack() (S8.8,
    wire_handler.cpp:583-593: read fresh on every ack/nack, i.e. on the
    NEXT wire line of ANY kind, not only another motion verb), simulated
    here by the direct last_done_reason() poll below.
    """
    _ready(wa)
    wa.set_now_ms(0)
    cpm = wa.counts_per_mm()

    declared_timeout_ms = 10_000  # a representative "generous" timeout
    distance_mm = 200.0
    dist_target_counts = distance_mm * cpm
    wa.feed(("MOVE_X 200 0 150 %d #1\n" % declared_timeout_ms).encode())
    assert wa.take_sink() == _ack(1)
    assert wa.has_live_motion_obligation()

    # The move reaches its own goal almost immediately (direct position
    # arming, same technique as test_move_x_reaching_its_own_goal_early_*
    # above -- not a hand-rolled duty-to-position physics model).
    wa.arm_motor_position(LEFT, dist_target_counts, sample_time_us=1)
    wa.arm_motor_position(RIGHT, dist_target_counts, sample_time_us=1)
    wa.step()
    still_active = wa.service_move()
    assert not still_active  # reached its own goal, well inside the window

    completion_ms = 50  # representative early-completion instant --
                         # mirrors the existing tests' own "~1000-1050ms
                         # against a several-thousand-ms deadline" shape
    wa.set_now_ms(completion_ms)
    assert wa.has_live_motion_obligation()  # nothing has POLLED yet

    assert wa.last_done_reason() == DONE_STOP  # the poll that notices it
    assert not wa.has_live_motion_obligation()  # post-003: closes right here

    # Quantify what this saves: pre-003, the fiber would have kept calling
    # tickDrive() (and therefore kernel.step()) roughly once per 24 ms for
    # the REST of the declared window, however many other polls happened
    # in between.
    tick_period_ms = 24  # shims.cpp's documented kernel.step() cadence
    avoided_ticks = (declared_timeout_ms - completion_ms) // tick_period_ms
    assert avoided_ticks == 414
