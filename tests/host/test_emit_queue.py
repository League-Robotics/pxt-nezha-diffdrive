"""tests/host/test_emit_queue.py -- the ring behind the outbound emit
path (comms/emit_queue.h).

**The defect this guards against.** The path this ring replaces used to
write straight to the transports from whatever fiber called it -- a
second producer racing the protocol fiber's own writes into the serial
driver, which is not safe against two producers. The fix makes the
protocol fiber the ring's only consumer: any fiber may enqueue, but
only a drain loop on one fiber ever reads a line back out and puts it
on the wire. This test proves the ring itself holds up its half of that
contract -- FIFO order preserved, and a burst bigger than capacity
counted rather than corrupting a line still waiting to be drained.

Run with::

    uv run pytest tests/host/test_emit_queue.py
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
        sources=[_TEST_DIR / "emit_queue_shim.cpp"],
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libemit_queue_shim.so",
    )))
    loaded.eqNew.restype = ctypes.c_void_p
    loaded.eqFree.argtypes = [ctypes.c_void_p]
    loaded.eqFree.restype = None
    loaded.eqEnqueue.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    loaded.eqEnqueue.restype = ctypes.c_int
    loaded.eqEnqueueLen.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    loaded.eqEnqueueLen.restype = ctypes.c_int
    loaded.eqDequeue.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    loaded.eqDequeue.restype = ctypes.c_int
    for n in ("eqCount", "eqSlots", "eqBytes"):
        getattr(loaded, n).argtypes = [ctypes.c_void_p]
        getattr(loaded, n).restype = ctypes.c_int
    loaded.eqDropped.argtypes = [ctypes.c_void_p]
    loaded.eqDropped.restype = ctypes.c_uint
    return loaded


class Q:
    def __init__(self, lib):
        self._l = lib
        self.h = ctypes.c_void_p(lib.eqNew())

    def __enter__(self): return self
    def __exit__(self, *a): self._l.eqFree(self.h)

    def put(self, s): return self._l.eqEnqueue(self.h, s.encode()) == 1
    def put_len(self, b, length): return self._l.eqEnqueueLen(self.h, b, length) == 1

    def pop(self):
        buf = ctypes.create_string_buffer(self.bytes())
        n = self._l.eqDequeue(self.h, buf, self.bytes())
        if n == 0:
            return None
        return buf.raw[:n].decode()

    def count(self): return self._l.eqCount(self.h)
    def dropped(self): return self._l.eqDropped(self.h)
    def slots(self): return self._l.eqSlots(self.h)
    def bytes(self): return self._l.eqBytes(self.h)


def test_fifo_order_preserved(lib):
    """The whole point: lines drain in the order they were queued, not
    reordered or overwritten by a later arrival."""
    with Q(lib) as q:
        lines = ["square:60", "pivot:90", "OCAL:1,2", "TOUR:end"]
        for text in lines:
            assert q.put(text)
        assert q.count() == len(lines)
        seen = []
        while True:
            line = q.pop()
            if line is None:
                break
            seen.append(line)
        assert seen == lines, f"not FIFO: {seen}"
        assert q.count() == 0


def test_overflow_is_counted_not_silent(lib):
    with Q(lib) as q:
        for i in range(q.slots()):
            assert q.put(f"cmd:{i}")
        assert q.dropped() == 0
        assert not q.put("one-too-many"), "a full ring must refuse, not overwrite"
        assert q.dropped() == 1
        assert not q.put("and-another")
        assert q.dropped() == 2


def test_burst_larger_than_capacity_does_not_corrupt_queued_text(lib):
    """A regression guard for the exact failure mode a shared-buffer or
    index-reuse bug would produce: once the ring is full, further
    enqueue() calls must count a drop and leave every already-queued
    line's text untouched, not overwrite or truncate it."""
    with Q(lib) as q:
        slots = q.slots()
        for i in range(slots):
            assert q.put(f"line-{i}")
        # a burst well past capacity
        for i in range(slots * 3):
            assert not q.put(f"overflow-{i}")
        assert q.dropped() == slots * 3
        assert q.count() == slots
        for i in range(slots):
            assert q.pop() == f"line-{i}"
        assert q.count() == 0


def test_drain_then_refill_reuses_slots(lib):
    with Q(lib) as q:
        for cycle in range(3):
            for i in range(q.slots()):
                assert q.put(f"cycle{cycle}:{i}")
            for i in range(q.slots()):
                assert q.pop() == f"cycle{cycle}:{i}"
        assert q.count() == 0
        assert q.dropped() == 0


def test_oversized_and_empty_are_refused_without_counting_a_drop(lib):
    """A malformed or empty line is not a capacity problem -- counting
    it as a drop would make the overflow counter lie about how many
    lines the caller actually lost to a full ring."""
    with Q(lib) as q:
        oversized = b"x" * (q.bytes() + 10)
        assert not q.put_len(oversized, len(oversized))
        assert not q.put_len(b"", 0)
        assert q.dropped() == 0
        assert q.count() == 0


def test_dequeue_on_empty_ring_returns_nothing(lib):
    with Q(lib) as q:
        assert q.pop() is None
        assert q.count() == 0
        assert q.dropped() == 0
