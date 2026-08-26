"""tests/host/test_encoder_glitch_armor.py -- host test for
src/core/encoder_glitch_armor.h's EncoderGlitchArmor (sprint 006 ticket 005,
clasi/issues/brick-reset-odometry-teleport.md /
clasi/sprints/006-*/issues/brick-reset-odometry-teleport.md, code review
R-07 / KERN-07 -- annex detail in
docs/code-review/2026-08-23/raw/correctness-kernel.md and
verify-kernel.md).

**The defect this fixes.** NezhaMotorPort::collect()'s pre-extraction
two-strike rule rejected an implausible raw-counts jump on its first
appearance, then ACCEPTED it as truth on a second, mutually-consistent
reading -- the documented hand-rotation re-sync path. That rule cannot
tell "the wheel really moved" apart from "the counter itself restarted"
(a brick MCU reset/brownout: encOffset_ captured once at begin() and
never re-baselined by any production path) -- both look identical from
the raw-counts stream alone: implausible first read, consistent second
read. This module adds the missing third outcome for that exact
trigger: kAcceptAsRebaseline, which the caller (NezhaMotorPort::collect(),
review-verified only -- see below) turns into an offset re-anchor
instead of integrating the jump as a ~4 m teleport.

**Why this is the only host-testable proxy for the fix.** `nezha_port.h`
includes pxt.h unconditionally, so `NezhaMotorPort` -- the actual call
site (`NezhaMotorPort::collect()`, src/platform/nezha_port.cpp) -- cannot be
compiled into any host test at all. `encoder_glitch_armor.h` carries the
ENTIRE plausibility decision that fix needs: a pure, hardware-free
function of the raw-counts stream. This suite exercises it directly.
Wiring it into `NezhaMotorPort::collect()` (the offset re-anchor, the
DIAG counter increment) is REVIEW-VERIFIED ONLY -- there is no existing
nezha_port.cpp-adjacent host test, and nothing in this ticket changes
that (tests/host/DESIGN.md S6's "not covered, by design" list already
names nezha_port explicitly).

Run with::

    uv run pytest tests/host/test_encoder_glitch_armor.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [_TEST_DIR / "encoder_glitch_armor_shim.cpp"]

# EncoderGlitchArmor::Decision's DECLARATION order (src/core/encoder_glitch_armor.h).
K_ACCEPT = 0
K_ACCEPT_AS_REBASELINE = 1
K_REJECT_PENDING = 2

# src/core/encoder_glitch_armor.h's own kMaxDeltaCounts -- duplicated here
# purely to size this test's own boundary cases (not to reimplement the
# decision: that lives in encoder_glitch_armor_shim.cpp, calling the
# real evaluate()). See that header for the full derivation from the
# kernel's 24 ms cycle period and its own measured fullDutyVelocity.
_MAX_DELTA_COUNTS = 5000


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libencoder_glitch_armor_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.egaCreate.argtypes = []
    loaded.egaCreate.restype = ctypes.c_void_p
    loaded.egaDestroy.argtypes = [ctypes.c_void_p]
    loaded.egaDestroy.restype = None
    loaded.egaSeedLastGoodRaw.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    loaded.egaSeedLastGoodRaw.restype = None
    loaded.egaMarkPrimed.argtypes = [ctypes.c_void_p]
    loaded.egaMarkPrimed.restype = None
    loaded.egaEvaluate.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    loaded.egaEvaluate.restype = ctypes.c_int
    loaded.egaLastGoodRaw.argtypes = [ctypes.c_void_p]
    loaded.egaLastGoodRaw.restype = ctypes.c_int32
    return loaded


class Armor:
    """Thin Pythonic wrapper around one egaCreate()/egaDestroy() handle,
    mirroring test_motion_engine_primitives.py's own Engine wrapper."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.egaCreate()

    def close(self):
        self._lib.egaDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def prime(self, raw):
        """Mirrors NezhaMotorPort::begin()'s own two calls when the
        initial median-of-3 read produced a usable sample."""
        self._lib.egaSeedLastGoodRaw(self._handle, raw)
        self._lib.egaMarkPrimed(self._handle)

    def evaluate(self, raw):
        return self._lib.egaEvaluate(self._handle, raw)

    def last_good_raw(self):
        return self._lib.egaLastGoodRaw(self._handle)


# ---- AC: plausible single reading (no jump) -- kAccept, unchanged ----

@pytest.mark.parametrize("delta", [0, 1, -1, 75, -75, _MAX_DELTA_COUNTS])
def test_plausible_single_reading_is_accepted_as_motion(lib, delta):
    """A reading within the plausibility bound -- including exactly AT
    the bound (mag == kMaxDeltaCounts, the strict `>` in evaluate() means
    this must still be plausible) -- is accepted as real motion on the
    first try, no second reading needed."""
    with Armor(lib) as armor:
        armor.prime(100_000)
        assert armor.evaluate(100_000 + delta) == K_ACCEPT
        assert armor.last_good_raw() == 100_000 + delta


def test_a_run_of_plausible_readings_stays_accepted(lib):
    """Sequential small steps (a genuinely rolling wheel) never trip the
    gate -- each step's delta is measured against the PREVIOUS accepted
    raw, not the original baseline."""
    with Armor(lib) as armor:
        armor.prime(0)
        raw = 0
        for step in (10, -5, 20, 3000, -2999, 4999):
            raw += step
            assert armor.evaluate(raw) == K_ACCEPT
            assert armor.last_good_raw() == raw


# ---- AC: implausible first reading, no consistent second -- kRejectPending ----

def test_implausible_first_reading_with_no_second_holds_pending(lib):
    """A single implausible jump, by itself, is held pending -- not
    accepted as motion and not (yet) treated as a rebaseline. This is
    the existing reject-and-wait path, unchanged by this ticket."""
    with Armor(lib) as armor:
        armor.prime(1000)
        decision = armor.evaluate(1000 + _MAX_DELTA_COUNTS + 1)
        assert decision == K_REJECT_PENDING
        # HOLD: last_good_raw must NOT have advanced to the rejected value.
        assert armor.last_good_raw() == 1000


def test_implausible_first_reading_followed_by_an_inconsistent_second_still_holds(lib):
    """Two implausible jumps in a row that are NOT mutually consistent
    (e.g. genuine bus noise on both reads, or the wheel spinning freely
    with no reset) must keep holding, not fall through to either accept
    path -- the two-strike rule requires the SECOND reading to agree with
    the FIRST rejected one, not merely to also be far from the last good
    value."""
    with Armor(lib) as armor:
        armor.prime(1000)
        assert armor.evaluate(1000 + 50_000) == K_REJECT_PENDING
        # Second reading is itself a big, DIFFERENT jump from the first
        # rejected value (50_000 + 1000 vs the first rejection's 51_000):
        # rejDelta = (51000+40000) - 51000 = 40000 >> threshold.
        assert armor.evaluate(1000 + 50_000 + 40_000) == K_REJECT_PENDING
        assert armor.last_good_raw() == 1000


# ---- AC: implausible-then-consistent (~50k reset-like jump) -- kAcceptAsRebaseline ----

def test_reset_like_jump_then_consistent_reading_is_accepted_as_rebaseline(lib):
    """The ticket's own named scenario: a brick MCU reset restarts the
    encoder counter near zero mid-session. The first post-reset read is
    an implausible jump (held pending); the SECOND post-reset read is
    close to the first (the reset counter incrementing normally) --
    mutually self-consistent, exactly the pattern the pre-extraction code
    used to accept as a real ~4 m teleport. This must now come back as
    kAcceptAsRebaseline, NOT kAccept."""
    with Armor(lib) as armor:
        # Pre-reset baseline, comparable in magnitude to R-07's own
        # ~50,000-count example.
        armor.prime(50_000)
        first = armor.evaluate(30)  # counter restarted near 0
        assert first == K_REJECT_PENDING
        assert armor.last_good_raw() == 50_000  # still holding pre-reset value

        second = armor.evaluate(75)  # counter incrementing normally post-reset
        assert second == K_ACCEPT_AS_REBASELINE
        # The armor's own notion of "last good" now tracks the NEW
        # (post-reset) counts stream -- the caller anchors its offset to
        # this, not to the pre-reset value.
        assert armor.last_good_raw() == 75


def test_rebaseline_then_further_motion_is_ordinary_accept(lib):
    """After a rebaseline fires, the armor must be back in normal
    operation -- subsequent small, plausible deltas against the NEW
    baseline are ordinary kAccept, not another two-strike cycle."""
    with Armor(lib) as armor:
        armor.prime(50_000)
        assert armor.evaluate(30) == K_REJECT_PENDING
        assert armor.evaluate(75) == K_ACCEPT_AS_REBASELINE
        assert armor.evaluate(120) == K_ACCEPT
        assert armor.last_good_raw() == 120


def test_hand_rotation_resync_still_works_the_same_two_strike_way(lib):
    """The ticket is explicit that the ORIGINAL hand-rotation re-sync
    trigger condition is unchanged -- only its outcome's LABEL changes
    (kAccept -> kAcceptAsRebaseline). A hand-repositioned wheel producing
    a large, self-consistent two-reading jump is exactly the same code
    path as a brick reset from this module's point of view: the
    disambiguation between "wheel really moved" and "counter restarted"
    is NOT decidable from raw counts alone (see R-07/KERN-07's own
    'hardware premise unverifiable' framing) -- it is the CALLER
    (NezhaMotorPort::collect(), review-verified only) that now chooses to
    treat this uniformly as a rebaseline rather than as integrated
    motion, which is the whole point of the fix."""
    with Armor(lib) as armor:
        armor.prime(0)
        assert armor.evaluate(20_000) == K_REJECT_PENDING
        assert armor.evaluate(20_050) == K_ACCEPT_AS_REBASELINE


# ---- Documented not-yet-primed corner case (pre-existing behavior) ----

def test_unprimed_armor_accepts_everything_unconditionally(lib):
    """Before markPrimed() is ever called (mirroring NezhaMotorPort::
    begin() never having run, or having run with zero usable samples),
    every reading is accepted -- however large the jump -- reproducing
    the pre-extraction inline code's own `if (primed_ && mag > ...)`
    guard exactly. This is a pre-existing corner case this ticket
    preserves, not a new relaxation."""
    with Armor(lib) as armor:
        assert armor.evaluate(0) == K_ACCEPT
        assert armor.evaluate(1_000_000) == K_ACCEPT
        assert armor.evaluate(-500_000) == K_ACCEPT
        assert armor.last_good_raw() == -500_000
