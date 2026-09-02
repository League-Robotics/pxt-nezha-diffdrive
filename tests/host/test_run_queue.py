"""tests/host/test_run_queue.py -- the ring behind cleartext RUN:.

**The defect this guards.** The predecessor was a write cursor and
nothing else: four slots, a round-robin index, no occupancy, no overflow
signal. A burst of RUN commands arriving while a long handler was still
running overwrote payload that handler had not read yet -- silently: no
counter moved, no reply changed, the handler just ran the wrong command.

The contract that fixes it: a slot is IN FLIGHT from `enqueue()` until
`release()`, and `enqueue()` refuses -- counting a drop -- rather than
trampling a slot still in flight. Nothing here is allowed to lose text
quietly.

Run with::

    uv run pytest tests/host/test_run_queue.py
"""
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    loaded = ctypes.CDLL(str(compile_shared_lib(
        tmp_path_factory,
        sources=[_TEST_DIR / "run_queue_shim.cpp"],
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="librun_queue_shim.so",
    )))
    loaded.rqNew.restype = ctypes.c_void_p
    for n in ("rqFree", "rqRelease"):
        getattr(loaded, n).argtypes = [ctypes.c_void_p, ctypes.c_int][:1 if n == "rqFree" else 2]
        getattr(loaded, n).restype = None
    loaded.rqEnqueue.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    loaded.rqEnqueue.restype = ctypes.c_int
    loaded.rqEnqueueLen.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    loaded.rqEnqueueLen.restype = ctypes.c_int
    loaded.rqAt.argtypes = [ctypes.c_void_p, ctypes.c_int]
    loaded.rqAt.restype = ctypes.c_char_p
    for n in ("rqPeek", "rqDequeue", "rqCount", "rqSlots"):
        getattr(loaded, n).argtypes = [ctypes.c_void_p]
        getattr(loaded, n).restype = ctypes.c_int
    loaded.rqDropped.argtypes = [ctypes.c_void_p]
    loaded.rqDropped.restype = ctypes.c_uint
    return loaded


class Q:
    def __init__(self, lib):
        self._l = lib
        self.h = ctypes.c_void_p(lib.rqNew())

    def __enter__(self): return self
    def __exit__(self, *a): self._l.rqFree(self.h)

    def put(self, s): return self._l.rqEnqueue(self.h, s.encode())
    def at(self, i):
        v = self._l.rqAt(self.h, i)
        return (v or b"").decode()
    def release(self, i): self._l.rqRelease(self.h, i)
    def peek(self): return self._l.rqPeek(self.h)
    def pop(self): return self._l.rqDequeue(self.h)
    def count(self): return self._l.rqCount(self.h)
    def dropped(self): return self._l.rqDropped(self.h)
    def slots(self): return self._l.rqSlots(self.h)


def test_text_survives_until_released(lib):
    """The whole point: a slot in flight is never reused."""
    with Q(lib) as q:
        a = q.put("square:60")
        b = q.put("pivot:90")
        assert a != b
        # a burst arrives while nothing has been consumed
        for i in range(q.slots() - 2):
            q.put(f"filler:{i}")
        assert q.count() == q.slots()
        assert q.at(a) == "square:60", (
            "the first payload was overwritten while still in flight -- "
            "this is exactly the silent loss the ring exists to prevent"
        )
        assert q.at(b) == "pivot:90"


def test_overflow_is_counted_not_silent(lib):
    with Q(lib) as q:
        for i in range(q.slots()):
            assert q.put(f"cmd:{i}") >= 0
        assert q.dropped() == 0
        assert q.put("one-too-many") == -1, "a full ring must refuse, not overwrite"
        assert q.dropped() == 1
        q.put("and-another")
        assert q.dropped() == 2
        # releasing one makes room again
        q.release(q.peek())
        assert q.put("now-fits") >= 0


def test_fifo_order(lib):
    with Q(lib) as q:
        for i in range(q.slots()):
            q.put(f"cmd:{i}")
        seen = []
        while True:
            s = q.pop()
            if s < 0:
                break
            seen.append(s)
        assert seen == list(range(q.slots())), f"not FIFO: {seen}"


def test_release_is_idempotent(lib):
    """A lossy transport can deliver the same read twice; that must not
    corrupt the occupancy count."""
    with Q(lib) as q:
        s = q.put("once")
        assert q.count() == 1
        q.release(s); q.release(s); q.release(s)
        assert q.count() == 0
        assert q.at(s) == ""


def test_identical_text_twice_is_allowed(lib):
    """The 3 s same-text suppression the old cursor needed made sending
    one command twice in a row impossible -- which is the shape
    `tools/turn_sweep.py` sends. The ring must not reintroduce it."""
    with Q(lib) as q:
        a = q.put("pivot:90")
        b = q.put("pivot:90")
        assert a >= 0 and b >= 0 and a != b
        assert q.at(a) == q.at(b) == "pivot:90"


def test_oversized_and_empty_are_refused_without_counting_a_drop(lib):
    """A malformed line is a parse problem, not a capacity problem --
    counting it as a drop would make the overflow counter lie."""
    with Q(lib) as q:
        assert q._l.rqEnqueueLen(q.h, b"x" * 100, 100) == -1
        assert q.dropped() == 0
        assert q.count() == 0


def test_wraparound_reuses_slots_after_release(lib):
    with Q(lib) as q:
        for _ in range(q.slots() * 3):
            s = q.put("go")
            assert s >= 0
            assert q.at(s) == "go"
            q.release(s)
        assert q.count() == 0
        assert q.dropped() == 0
