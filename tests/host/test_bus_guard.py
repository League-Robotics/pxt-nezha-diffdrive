"""tests/host/test_bus_guard.py -- host test for src/core/bus_guard.h's
BusGuard (sprint 030 ticket 001,
clasi/sprints/030-bus-discipline-and-fiber-safety/issues/
enforce-the-one-fiber-i2c-invariant.md, code review 2026-09-02 RC-01 /
CM-03 / BT-04 / BT-05).

**What this fixes.** `tickDrive()` (src/shims.cpp) already serialized
`kernel.step()` against a second fiber also calling `tickDrive()`, via a
bare `bool` (`Rig::stepBusy`) checked-and-set with no intervening yield.
Nothing else that touches the shared I2C bus took that same guard: every
OTOS shim entry point issued I2C unconditionally, so an OTOS transaction
could land inside the Nezha encoder's own select->read settle window and
destroy that encoder sample (the documented Phase-F signature,
src/platform/nezha_port.cpp:376-380). This ticket promotes the bare flag
to `BusGuard`, a small class both `tickDrive()` and every OTOS entry
point now share.

**Why this is the only host-testable proxy for the fix.** `otos_port.h`
includes pxt.h unconditionally, so `OtosPort` -- the actual OTOS I2C
call sites (src/platform/otos_port.cpp) -- cannot be compiled into any
host test at all, and `shims.cpp` (the six guarded entry points) pulls
in pxt.h too. `bus_guard.h` carries the ENTIRE mutual-exclusion decision
those call sites now share: a pure, hardware-free acquire/release pair
over one `DiffDrive::Sleeper`. This suite exercises it directly. Wiring
`r.busGuard.acquire()/release()` into `tickDrive()` and the six shims.cpp
OTOS entry points is pinned instead by
tests/host/test_bus_guard_source_pin.py (grep-based, since neither file
can be host-compiled).

Run with::

    uv run pytest tests/host/test_bus_guard.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [_TEST_DIR / "bus_guard_shim.cpp"]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libbus_guard_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.bgCreate.argtypes = []
    loaded.bgCreate.restype = ctypes.c_void_p
    loaded.bgDestroy.argtypes = [ctypes.c_void_p]
    loaded.bgDestroy.restype = None
    loaded.bgAcquire.argtypes = [ctypes.c_void_p]
    loaded.bgAcquire.restype = None
    loaded.bgRelease.argtypes = [ctypes.c_void_p]
    loaded.bgRelease.restype = None
    loaded.bgHeld.argtypes = [ctypes.c_void_p]
    loaded.bgHeld.restype = ctypes.c_bool
    loaded.bgSleepCalls.argtypes = [ctypes.c_void_p]
    loaded.bgSleepCalls.restype = ctypes.c_int
    loaded.bgArmReleaseOnSleepCall.argtypes = [ctypes.c_void_p, ctypes.c_int]
    loaded.bgArmReleaseOnSleepCall.restype = None
    loaded.bgDisarm.argtypes = [ctypes.c_void_p]
    loaded.bgDisarm.restype = None
    return loaded


class Guard:
    """Thin Pythonic wrapper around one bgCreate()/bgDestroy() handle,
    mirroring test_encoder_glitch_armor.py's own Armor wrapper."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.bgCreate()

    def close(self):
        self._lib.bgDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def acquire(self):
        self._lib.bgAcquire(self._handle)

    def release(self):
        self._lib.bgRelease(self._handle)

    def held(self):
        return bool(self._lib.bgHeld(self._handle))

    def sleep_calls(self):
        return self._lib.bgSleepCalls(self._handle)

    def arm_release_on_sleep_call(self, sleep_call_number):
        self._lib.bgArmReleaseOnSleepCall(self._handle, sleep_call_number)

    def disarm(self):
        self._lib.bgDisarm(self._handle)


def test_first_acquire_on_a_free_bus_does_not_sleep(lib):
    """A guard nobody holds is claimed immediately -- no spin, no
    sleepMillis() calls at all. Matches stepBusy's own pre-extraction
    behavior: the `while (busy_)` loop body never runs when busy_ starts
    false."""
    with Guard(lib) as guard:
        guard.acquire()
        assert guard.sleep_calls() == 0


def test_acquire_waits_until_the_scripted_release_lands(lib):
    """The Acceptance Criteria's own scenario: script FakeSleeper::onSleep
    to fire while BusGuard::acquire() is mid-spin, and confirm the
    caller does not proceed until release() is called from that
    callback. Arms the release at the 3rd sleepMillis() call -- the
    second acquire() must therefore block for EXACTLY 3 sleep calls, no
    fewer (it must not sneak past the still-held guard early) and no
    more (it must not spin forever once release() has actually landed)."""
    with Guard(lib) as guard:
        guard.acquire()  # first holder claims the bus, no sleep needed
        assert guard.sleep_calls() == 0

        guard.arm_release_on_sleep_call(3)
        guard.acquire()  # second holder must wait for the scripted release
        assert guard.sleep_calls() == 3


def test_a_shorter_or_longer_contention_window_changes_the_wait_exactly(lib):
    """Same scenario at a different scripted delay, proving the wait
    tracks the release point rather than some fixed/short-circuited
    count."""
    with Guard(lib) as guard:
        guard.acquire()
        guard.arm_release_on_sleep_call(1)
        guard.acquire()
        assert guard.sleep_calls() == 1

    with Guard(lib) as guard:
        guard.acquire()
        guard.arm_release_on_sleep_call(7)
        guard.acquire()
        assert guard.sleep_calls() == 7


def test_released_guard_can_be_acquired_again_with_no_further_wait(lib):
    """acquire() -> release() -> acquire() again on a now-free bus must
    not carry over any stale contention state -- the second acquire()
    here is uncontended and must not sleep."""
    with Guard(lib) as guard:
        guard.acquire()
        guard.release()
        guard.acquire()  # bus is free again
        assert guard.sleep_calls() == 0


def test_release_without_a_prior_acquire_leaves_the_guard_free(lib):
    """release() on a never-acquired guard is a harmless no-op (matches
    stepBusy's own pre-extraction contract: a bare flag write, no
    defensive re-check) -- a subsequent acquire() still succeeds without
    waiting."""
    with Guard(lib) as guard:
        guard.release()
        guard.acquire()
        assert guard.sleep_calls() == 0


# ---- held(): the non-blocking peek a staged-stop caller needs ----------

def test_held_is_false_on_a_fresh_never_acquired_guard(lib):
    """A guard nobody has ever touched reads as not-held -- the same
    default a caller must be able to trust before its first acquire()."""
    with Guard(lib) as guard:
        assert guard.held() is False


def test_held_is_true_between_acquire_and_release(lib):
    """The whole point of this accessor: a caller that must never block
    (a staged-stop decision) can tell "someone is mid-transaction" apart
    from "the bus is free" without spinning through acquire() itself."""
    with Guard(lib) as guard:
        guard.acquire()
        assert guard.held() is True
        guard.release()
        assert guard.held() is False


def test_held_reflects_the_scripted_mid_spin_release_too(lib):
    """held() must track the SAME busy_ state acquire()'s own spin loop
    waits on -- confirmed here via the identical scripted-release seam
    the contention tests above use, so this is not a second, drifting
    notion of "held"."""
    with Guard(lib) as guard:
        guard.acquire()
        assert guard.held() is True
        guard.arm_release_on_sleep_call(2)
        guard.acquire()  # second holder waits, then the callback releases
        assert guard.held() is True  # ...and immediately reclaims it
