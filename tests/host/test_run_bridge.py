"""tests/host/test_run_bridge.py -- the RUN bridge's own
sanitize / park / bypass rules, exercised with no `Protocol` in
the link.

**Why this file exists.** These rules used to live inline in
`src/comms/protocol.cpp`, which includes `pxt.h` transitively and so
cannot be compiled -- let alone executed -- by anything under
`tests/host/`. Every property below was therefore either unpinned or
pinned only as *source text* (`test_run_abort_source_pin.py`, which can
assert that a bypass exists in the right order but never that it
behaves). `src/comms/run_bridge.h/.cpp` is the same host-portable
extraction `run_queue.h` already is, so the behavior itself is now
reachable: this file drives the real object through `ctypes` and
asserts on what it does, not on how its source reads.

**The two properties worth protecting**, both of them ones a bench host
can observe going wrong:

1. **`abort` / `clearestop` skip the queue.** A queued abort sits behind
   the very job it was sent to stop, because a consumer refuses to start
   a second job while one already owns the drivetrain.
2. **A full ring refuses and COUNTS.** Overwriting a slot still in
   flight makes a handler run a command nobody sent, silently.

A third property, repeat suppression, was deleted on 2026-09-07 along
with the cleartext `RUN:` carve-out this bridge used to serve. It was a
400 ms same-text window standing in for sequence numbers the carve-out
did not have; the v6 reliability layer now does that job exactly, one
layer up, by re-acking a retransmit's original `#id` without
re-executing it. The tests for it went with the code.

Run with::

    uv run pytest tests/host/test_run_bridge.py
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
        sources=[
            _SRC_DIR / "comms" / "run_bridge.cpp",
            _TEST_DIR / "run_bridge_shim.cpp",
        ],
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="librun_bridge_shim.so",
    )))
    loaded.rbNew.restype = ctypes.c_void_p
    loaded.rbFree.argtypes = [ctypes.c_void_p]
    loaded.rbFree.restype = None
    loaded.rbOffer.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    loaded.rbOffer.restype = ctypes.c_int
    loaded.rbOfferText.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    loaded.rbOfferText.restype = ctypes.c_int
    for name in ("rbDispatchOne", "rbQueued"):
        getattr(loaded, name).argtypes = [ctypes.c_void_p]
        getattr(loaded, name).restype = ctypes.c_int
    loaded.rbCurrentText.argtypes = [ctypes.c_void_p]
    loaded.rbCurrentText.restype = ctypes.c_char_p
    loaded.rbDropCount.argtypes = [ctypes.c_void_p]
    loaded.rbDropCount.restype = ctypes.c_uint
    loaded.rbMalformedCount.argtypes = [ctypes.c_void_p]
    loaded.rbMalformedCount.restype = ctypes.c_uint
    loaded.rbIsBypassName.argtypes = [ctypes.c_char_p]
    loaded.rbIsBypassName.restype = ctypes.c_int
    for name in ("rbSlots", "rbTextBytes",
                 "rbOfferCodeMalformed",
                 "rbOfferCodeBypass", "rbOfferCodeQueued",
                 "rbOfferCodeDropped"):
        getattr(loaded, name).argtypes = []
        getattr(loaded, name).restype = ctypes.c_int
    return loaded


class Bridge:
    """Thin Python face on one RunBridge instance."""

    def __init__(self, lib):
        self._l = lib
        self.h = ctypes.c_void_p(lib.rbNew())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._l.rbFree(self.h)

    def offer(self, text):
        """`text` may be bytes (raw payload, sent verbatim) or str."""
        if isinstance(text, str):
            text = text.encode()
        return self._l.rbOffer(self.h, text, len(text))

    def dispatch_one(self):
        return bool(self._l.rbDispatchOne(self.h))

    def current(self):
        return (self._l.rbCurrentText(self.h) or b"").decode()

    def queued(self):
        return self._l.rbQueued(self.h)

    def dropped(self):
        return self._l.rbDropCount(self.h)

    def malformed(self):
        return self._l.rbMalformedCount(self.h)


@pytest.fixture
def codes(lib):
    return {
        "malformed": lib.rbOfferCodeMalformed(),
        "bypass": lib.rbOfferCodeBypass(),
        "queued": lib.rbOfferCodeQueued(),
        "dropped": lib.rbOfferCodeDropped(),
    }


# ---------------------------------------------------------------------------
# offer() / dispatchOne() / currentText(): the ordinary path
# ---------------------------------------------------------------------------


def test_a_parked_payload_comes_back_out_of_dispatch_one(lib, codes):
    with Bridge(lib) as b:
        assert b.offer("pivot:180") == codes["queued"]
        assert b.queued() == 1
        assert b.dispatch_one() is True
        assert b.current() == "pivot:180"
        assert b.queued() == 0, "dispatchOne() must release the slot it staged"


def test_dispatch_one_says_no_when_nothing_is_parked(lib):
    with Bridge(lib) as b:
        assert b.current() == "", "no payload has ever been staged"
        assert b.dispatch_one() is False
        assert b.current() == "", "a refused dispatch must not stage anything"


def test_parked_payloads_are_staged_in_arrival_order(lib, codes):
    with Bridge(lib) as b:
        for text in ("square:60", "pivot:90", "straight:20"):
            assert b.offer(text) == codes["queued"]
        seen = []
        while b.dispatch_one():
            seen.append(b.current())
        assert seen == ["square:60", "pivot:90", "straight:20"]


def test_a_trailing_carriage_return_is_stripped(lib, codes):
    """A raw terminal sends CRLF; the payload is the same command."""
    with Bridge(lib) as b:
        assert b.offer(b"pivot:90\r") == codes["queued"]
        assert b.dispatch_one()
        assert b.current() == "pivot:90"


@pytest.mark.parametrize("payload", [
    b"",                      # nothing at all
    b"\r",                    # nothing once the CR is stripped
    b":180",                  # empty name -- nothing to dispatch on
    b"pivot:\x01",            # not printable ASCII
    b"x" * 48,                # exactly one byte too long for a slot
])
def test_malformed_payloads_are_refused_without_touching_the_queue(
        lib, codes, payload):
    """A malformed line is a parse problem, not a capacity problem --
    counting it as a drop would make the overflow counter lie."""
    with Bridge(lib) as b:
        assert b.offer(payload) == codes["malformed"]
        assert b.queued() == 0
        assert b.dropped() == 0


# ---------------------------------------------------------------------------
# The malformed counter
# ---------------------------------------------------------------------------
#
# Every refusal above used to be a bare return: the payload vanished
# and nothing anywhere said so. From the relay that is indistinguishable
# from radio loss, and a 48-character `RUN:tour:...` line with several
# numeric arguments is a realistic way to hit it.


@pytest.mark.parametrize("payload,shape", [
    (b"x" * 48, "overlong -- exactly one byte too long for a slot"),
    (b"pivot:\x01", "not printable ASCII"),
    (b":180", "empty name"),
    (b"", "empty payload"),
    (b"\r", "empty once the CR is stripped"),
])
def test_every_refusal_shape_increments_the_malformed_counter(
        lib, codes, payload, shape):
    with Bridge(lib) as b:
        assert b.malformed() == 0
        assert b.offer(payload) == codes["malformed"], shape
        assert b.malformed() == 1, shape
        assert b.dropped() == 0, (
            f"{shape}: a malformed line must not move the CAPACITY "
            f"counter -- they answer different questions"
        )


def test_the_malformed_counter_accumulates_across_shapes(lib, codes):
    """One counter for all the refusal shapes, per the remedy -- not one
    each. The operator's question is "is this link feeding me garbage",
    not which flavour."""
    with Bridge(lib) as b:
        for payload in (b"y" * 60, b"\x7f", b":a", b""):
            assert b.offer(payload) == codes["malformed"]
        assert b.malformed() == 4


def test_accepted_payloads_leave_the_counter_alone(lib, codes):
    """A counter that also moved on ordinary traffic would be useless as
    a "something is wrong" signal."""
    with Bridge(lib) as b:
        assert b.offer("pivot:90") == codes["queued"]
        assert b.offer("pivot:90") == codes["queued"]
        assert b.offer("abort") == codes["bypass"]
        assert b.malformed() == 0


# ---------------------------------------------------------------------------
# The abort / clearestop bypass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["abort", "clearestop"])
def test_the_bypass_names_skip_the_queue_and_are_staged_immediately(
        lib, codes, name):
    with Bridge(lib) as b:
        assert b.offer("tour:1") == codes["queued"]
        assert b.offer(name) == codes["bypass"]
        assert b.current() == name, (
            "a bypass must stage its own payload -- the caller dispatches "
            "immediately and reads it back with no dequeue step"
        )
        assert b.queued() == 1, (
            f"{name} was parked behind the running job -- it would take "
            f"effect only after the very job it was sent to stop"
        )


def test_the_bypass_matches_on_the_name_only_not_the_arguments(lib, codes):
    """`name` is the payload up to (not including) its first ':', the
    same split the TypeScript dispatcher makes."""
    with Bridge(lib) as b:
        assert b.offer("abort:now") == codes["bypass"]
        assert b.current() == "abort:now", (
            "the WHOLE payload is staged; only the match is name-only"
        )


@pytest.mark.parametrize("payload", ["abortive", "ab", "clearestops",
                                     "tour:abort"])
def test_names_that_merely_resemble_the_bypass_are_queued(lib, codes, payload):
    with Bridge(lib) as b:
        assert b.offer(payload) == codes["queued"]
        assert b.queued() == 1


def test_is_bypass_name_is_callable_without_an_instance(lib):
    """The rule is a property of the vocabulary, not of any one
    bridge's state -- a consumer can ask it directly."""
    assert lib.rbIsBypassName(b"abort") == 1
    assert lib.rbIsBypassName(b"clearestop:1") == 1
    assert lib.rbIsBypassName(b"pivot:90") == 0


def test_a_bypass_does_not_disturb_what_is_already_parked(lib, codes):
    with Bridge(lib) as b:
        assert b.offer("square:60") == codes["queued"]
        assert b.offer("abort") == codes["bypass"]
        assert b.dispatch_one() is True
        assert b.current() == "square:60", (
            "the bypass consumed a queued slot -- it must not dequeue"
        )
        assert b.dispatch_one() is False


def test_a_repeated_bypass_always_executes(lib, codes):
    """Nothing may stand between these two names and the drivetrain --
    not a queue, and (since 2026-09-07) not a suppression window either.
    The 400 ms same-text window this bridge used to run ate the second
    `abort` of a doubled press; it is gone, and the v6 sequence layer
    that replaced it suppresses only a genuine retransmit (same `#id`),
    never a deliberate repeat under a fresh one.

    Safe because both bypass handlers are idempotent (stop what is
    running; clear a latch that may already be clear) -- the same
    property that made them safe to invoke reentrantly from inside a
    running job."""
    with Bridge(lib) as b:
        assert b.offer("abort") == codes["bypass"]
        assert b.offer("abort") == codes["bypass"]
        assert b.offer("clearestop") == codes["bypass"]
        assert b.offer("clearestop") == codes["bypass"]
        assert b.queued() == 0, "a bypass never parks"


def test_an_ordinary_repeat_is_queued_every_time(lib, codes):
    """The bridge itself no longer de-duplicates ANYTHING: two identical
    ordinary payloads are two jobs. That is correct now, because the
    only way a repeat reaches here is a host deliberately sending a
    second `RUN` under a fresh `#id` -- a retransmit reuses its original
    id and is stopped by the reliability layer, upstream of this file,
    without ever being offered."""
    with Bridge(lib) as b:
        assert b.offer("tour:1") == codes["queued"]
        assert b.offer("tour:1") == codes["queued"]
        assert b.queued() == 2


# ---------------------------------------------------------------------------
# Ring overflow
# ---------------------------------------------------------------------------


def test_a_full_ring_refuses_and_counts(lib, codes):
    slots = lib.rbSlots()
    with Bridge(lib) as b:
        for i in range(slots):
            assert b.offer(f"cmd:{i}") == codes["queued"]
        assert b.queued() == slots
        assert b.dropped() == 0
        assert b.offer("one-too-many") == codes["dropped"], (
            "a full ring must refuse, not overwrite a slot still in flight"
        )
        assert b.dropped() == 1
        assert b.offer("and-another") == codes["dropped"]
        assert b.dropped() == 2
        # The payloads that WERE accepted are all still intact and in
        # order -- that is what the refusal buys.
        assert b.dispatch_one() and b.current() == "cmd:0"
        assert b.offer("now-fits") == codes["queued"]


def test_a_resent_payload_is_dropped_again_while_the_ring_stays_full(
        lib, codes):
    """With suppression gone, a resend of a dropped command is offered
    to the ring again rather than being swallowed by a time window --
    and is refused again, and counted again, while the ring is still
    full. Two drops, not one: the host is told twice, which is correct,
    because it asked twice and neither ran."""
    slots = lib.rbSlots()
    with Bridge(lib) as b:
        for i in range(slots):
            assert b.offer(f"cmd:{i}") == codes["queued"]
        assert b.offer("overflowing") == codes["dropped"]
        assert b.offer("overflowing") == codes["dropped"]
        assert b.dropped() == 2


# ---------------------------------------------------------------------------
# Sizing constants
# ---------------------------------------------------------------------------


def test_the_ring_matches_the_slot_and_payload_sizing_it_replaced(lib):
    """RunBridge's ring is run_queue.h's, at the same 8 x 48 sizing the
    inline version used -- a payload that fit before must still fit."""
    assert lib.rbSlots() == 8
    assert lib.rbTextBytes() == 48
