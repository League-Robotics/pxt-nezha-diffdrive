"""tests/host/test_motion_owner.py -- host test for
src/core/motion_owner.h's MotionOwner enum and its kBlock take/release
arbitration (sprint 030 ticket 002,
clasi/sprints/030-bus-discipline-and-fiber-safety/issues/
service-hook-must-check-fiber-identity.md).

**What this fixes.** Before this ticket, `motionOwner_` (kNone/kWire/
kJob) never arbitrated the block program's own fiber at all: startMove()/
driveTwist()/startDrive() called the engine unconditionally, so a
button-handler tour could supersede a live wire move with no
arbitration -- the wire's own completion channel then resolved that
superseded move as an ordinary stop, indistinguishable from one the
host itself caused. This adds a fourth owner, kBlock, and the one rule
a block-motion entry point applies before it ever touches the engine:
take kBlock iff nothing else currently holds the drivetrain, otherwise
refuse -- never silently supersede.

**Why this is the host-testable half.** The real call sites
(src/shims.cpp's startMove()/driveTwist()/engineGoToRArmed(), and
comms/protocol.cpp's own Protocol::tryTakeMotionOwnership()/
releaseBlockOwnership() wrapping this same rule around the
CODAL-visible motionOwner_ field) all include pxt.h and cannot be
host-compiled. motion_owner.h carries the ENTIRE arbitration decision
those call sites share: a pure take-or-refuse function over one
MotionOwner value. This suite exercises it directly -- decision-logic
coverage, not proof that shims.cpp actually calls it (that is a
source-reading / code-review check, documented in the ticket's own
report, and ultimately a hardware acceptance concern).

**sprint 031 ticket 017 addition.** `tryTakeBlockOwnership()` above is
the plain kBlock rule; it refuses unconditionally whenever anything
else (kWire, kJob, or an already-taken kBlock) holds the drivetrain.
That is CORRECT for a genuine block-program caller, but it is also
what `Protocol::tryTakeMotionOwnership()` used to call UNCONDITIONALLY
for every caller -- including a dispatched RUN job's own move, which
runs synchronously inside `dispatchJob()`'s call into the TS handler
with `motionOwner_` already `kJob`, and was therefore refused by its
OWN dispatch (the ticket's whole defect: `RUN:straight:8` moved the
robot 0.02 cm). `tryTakeMotionOwnership()` below is the fix: it
recognizes that case (via an `isDispatchingFiber` bool the CODAL-facing
caller computes by fiber identity, exactly as
`shouldServiceHookRun()`/`test_fiber_identity_gate.py` already does for
the tick service hook) and lets it through unchanged, while still
applying the UNCHANGED `tryTakeBlockOwnership()` rule -- refused, never
superseding -- to every other caller. `test_kblock_ownership_source_pin.py`
pins that shims.cpp's three entry points call this new function, not
the plain one.

Run with::

    uv run pytest tests/host/test_motion_owner.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [_TEST_DIR / "motion_owner_shim.cpp"]

# MotionOwner's own declaration-order ordinal (src/core/motion_owner.h).
K_NONE = 0
K_WIRE = 1
K_JOB = 2
K_BLOCK = 3


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libmotion_owner_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.motionOwnerTryTakeBlockOwnership.argtypes = [ctypes.c_int]
    loaded.motionOwnerTryTakeBlockOwnership.restype = ctypes.c_int
    loaded.motionOwnerReleaseBlockOwnership.argtypes = [ctypes.c_int]
    loaded.motionOwnerReleaseBlockOwnership.restype = ctypes.c_int
    loaded.motionOwnerTryTakeMotionOwnership.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
    ]
    loaded.motionOwnerTryTakeMotionOwnership.restype = ctypes.c_int
    return loaded


def test_take_succeeds_from_none_and_becomes_block(lib):
    """The idle case: nothing owns the drivetrain, so a block-motion
    entry point's own take succeeds and the owner becomes kBlock."""
    assert lib.motionOwnerTryTakeBlockOwnership(K_NONE) == K_BLOCK


@pytest.mark.parametrize("held_by", [K_WIRE, K_JOB, K_BLOCK])
def test_take_is_refused_while_anything_else_holds_it(lib, held_by):
    """The Acceptance Criteria's own scenario: a block-motion call while
    motionOwner_ == kWire (or kJob, or an already-taken kBlock) is
    refused, never silently superseding -- signaled here as -1 (no
    ordinal is negative), matching the seam's own contract
    (motion_owner.h: "leave `*owner` untouched and return false")."""
    assert lib.motionOwnerTryTakeBlockOwnership(held_by) == -1


def test_release_from_block_drops_to_none(lib):
    """The mirror of dispatchJob()'s own take/release span for kJob: a
    block-motion entry point's own release, once its move ends, drops
    the owner all the way back to idle."""
    assert lib.motionOwnerReleaseBlockOwnership(K_BLOCK) == K_NONE


@pytest.mark.parametrize("held_by", [K_NONE, K_WIRE, K_JOB])
def test_release_is_a_no_op_unless_currently_block(lib, held_by):
    """Defensive half of the same rule: a release call can never
    clobber a DIFFERENT owner's still-live claim -- only a caller that
    actually holds kBlock can ever clear it."""
    assert lib.motionOwnerReleaseBlockOwnership(held_by) == held_by


# ---- sprint 031 ticket 017: tryTakeMotionOwnership() ----------------------
#
# This is the test that FAILS against the pre-fix behavior: before this
# ticket there was no way to express "a dispatched job's own call, on
# the dispatching fiber, must proceed" at all -- every take was the
# plain kBlock rule above, which refuses unconditionally under kJob.
# The critical case below (kJob + dispatching fiber -> succeeds,
# unchanged) is exactly the scenario that was silently refused on
# hardware (RUN:straight:8 moved 0.02 cm, captures/session-b-20260905/
# notes.md).

def test_dispatching_fibers_own_job_call_proceeds_unchanged(lib):
    """The bug this ticket fixes: motionOwner_ is kJob (dispatchJob()
    set it before calling the TS handler synchronously, on ITS OWN
    fiber) and the handler's own startMove()/driveTwist()/
    engineGoToRArmed() call arrives on that SAME fiber. This must
    succeed, and must NOT change the owner away from kJob -- there is
    no new ownership here for anything to release later; dispatchJob()
    itself still owns clearing kJob once runDispatch() returns."""
    assert lib.motionOwnerTryTakeMotionOwnership(K_JOB, 1) == K_JOB


@pytest.mark.parametrize("held_by", [K_WIRE, K_BLOCK])
def test_dispatching_fiber_still_refused_unless_owner_is_job(lib, held_by):
    """Defensive: `isDispatchingFiber` alone is not a blanket bypass --
    the bypass only fires when motionOwner_ is ALREADY kJob (the one
    state dispatchJob() itself can put the protocol fiber in). Under
    kWire or kBlock, a call arriving on the protocol fiber falls through
    to the ordinary kBlock rule and is refused exactly as before."""
    assert lib.motionOwnerTryTakeMotionOwnership(held_by, 1) == -1


def test_dispatching_fiber_from_none_takes_kblock_like_normal(lib):
    """Edge case, not reachable in production (the protocol fiber only
    ever calls a motion entry point from INSIDE dispatchJob(), which
    always sets kJob first) but pinned so the fallthrough's own
    behavior stays honest: with nothing held, the ordinary kBlock take
    still applies regardless of which fiber is asking."""
    assert lib.motionOwnerTryTakeMotionOwnership(K_NONE, 1) == K_BLOCK


def test_a_genuine_block_caller_is_still_refused_while_a_job_runs(lib):
    """THE ACCEPTANCE CRITERION this ticket must preserve: a genuine
    block-program caller (a button, a student script -- NOT the
    dispatching fiber) arriving while motionOwner_ == kJob is refused,
    never silently superseding -- verified on hardware, sprint 031
    ticket 009 Item 2(b). Identical to
    test_take_is_refused_while_anything_else_holds_it above, restated
    through the new combined entry point so a future change to it
    cannot silently drop this refusal."""
    assert lib.motionOwnerTryTakeMotionOwnership(K_JOB, 0) == -1


@pytest.mark.parametrize("held_by", [K_WIRE, K_BLOCK])
def test_a_genuine_block_caller_is_refused_under_wire_or_block_too(
    lib, held_by
):
    """The remaining two refusal cases, unchanged from the plain kBlock
    rule: a non-dispatching caller under a live wire motion or an
    already-taken kBlock is refused."""
    assert lib.motionOwnerTryTakeMotionOwnership(held_by, 0) == -1


def test_a_genuine_block_caller_from_none_takes_kblock(lib):
    """The ordinary, most common case, restated through the new entry
    point: nothing owns the drivetrain, a real block call (not the
    dispatching fiber) takes kBlock."""
    assert lib.motionOwnerTryTakeMotionOwnership(K_NONE, 0) == K_BLOCK
