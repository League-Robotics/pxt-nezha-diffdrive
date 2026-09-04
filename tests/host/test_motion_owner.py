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
comms/protocol.cpp's own Protocol::tryTakeBlockOwnership()/
releaseBlockOwnership() wrapping this same rule around the
CODAL-visible motionOwner_ field) all include pxt.h and cannot be
host-compiled. motion_owner.h carries the ENTIRE arbitration decision
those call sites share: a pure take-or-refuse function over one
MotionOwner value. This suite exercises it directly -- decision-logic
coverage, not proof that shims.cpp actually calls it (that is a
source-reading / code-review check, documented in the ticket's own
report, and ultimately a hardware acceptance concern).

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
