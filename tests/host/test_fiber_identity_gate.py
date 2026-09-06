"""tests/host/test_fiber_identity_gate.py -- host test for
src/core/fiber_identity.h's shouldServiceHookRun() (sprint 030 ticket
002, clasi/sprints/030-bus-discipline-and-fiber-safety/issues/
service-hook-must-check-fiber-identity.md).

**What this fixes.** `Protocol::serviceHookEntry()` used to gate on
`motionOwner_ == kJob` -- a piece of STATE -- not on which fiber was
calling tickDrive(). A button-handler tour running on its own CODAL
MessageBus fiber during a live RUN job satisfied that state check and
ran serviceOnce() a second time, concurrently with the protocol fiber's
own call -- corrupting the wire dispatcher's shared line buffer mid-
yield (the ack write yields; the second fiber's own feed() overwrote
the buffer during that yield). The fix compares fiber IDENTITY instead:
the hook may only ever run on the one fiber Protocol::run() itself
executes on, regardless of what motionOwner_ says.

**Why this is the host-testable half, and only the decision-logic
half.** comms/protocol.cpp includes pxt.h (directly and transitively),
so Protocol::serviceHookEntry() and a real CODAL fiber cannot be
exercised host-side at all. fiber_identity.h carries the ENTIRE
comparison that function makes -- a pure, hardware-free function of two
opaque ids. This suite pins that decision directly: given fiber A's id
captured as "the protocol fiber" and a call presenting fiber B's id,
the gate answers false (the hook must not invoke serviceOnce()); given
fiber A calling with fiber A's own id, it answers true. This is
decision-logic coverage, not end-to-end proof that the real hook wiring
never runs on a second fiber on real hardware -- that remains a
hardware-only acceptance step.

Run with::

    uv run pytest tests/host/test_fiber_identity_gate.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [_TEST_DIR / "fiber_identity_shim.cpp"]

# Two distinct fake fiber ids -- opaque, arbitrary, and distinct is all
# the gate ever requires of them (see fiber_identity_shim.cpp's own
# header comment).
FIBER_A = 0x1000
FIBER_B = 0x2000


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libfiber_identity_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.fiberIdentityShouldServiceHookRun.argtypes = [
        ctypes.c_longlong,
        ctypes.c_longlong,
    ]
    loaded.fiberIdentityShouldServiceHookRun.restype = ctypes.c_int
    return loaded


def test_the_protocol_fibers_own_call_runs_the_hook(lib):
    """The one caller the hook must always serve: the same fiber that
    was captured as the protocol fiber, calling again."""
    assert lib.fiberIdentityShouldServiceHookRun(FIBER_A, FIBER_A) == 1


def test_a_second_fibers_call_never_runs_the_hook(lib):
    """The Acceptance Criteria's own scenario: fiber A's id was captured
    as "the protocol fiber", and a call presents fiber B's id -- the
    hook must not run serviceOnce(), regardless of what motionOwner_
    would have said under the old check."""
    assert lib.fiberIdentityShouldServiceHookRun(FIBER_A, FIBER_B) == 0


def test_an_uncaptured_protocol_fiber_id_never_runs_the_hook(lib):
    """Before Protocol::run() has ever executed, protocolFiberId_ is
    null -- no fiber has been registered as "the" protocol fiber yet,
    so nothing can match it, not even a call presenting that same null
    value."""
    assert lib.fiberIdentityShouldServiceHookRun(0, 0) == 0
    assert lib.fiberIdentityShouldServiceHookRun(0, FIBER_B) == 0
