"""tests/host/test_run_bridge.py -- the cleartext RUN bridge's own
sanitize / dedupe / park / bypass rules, exercised with no `Protocol` in
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

**The three properties worth protecting**, all of them ones a bench host
can observe going wrong:

1. **Dedupe is applied at ARRIVAL, not at handling.** A host repeats
   commands to survive the robot's single-slot inbound wireless buffer;
   without suppression each copy executes. Suppressing at handling time
   instead would make the window depend on how long the queue happened
   to be -- the window has to bound the retransmit burst, and nothing
   else.
2. **`abort` / `clearestop` skip the queue.** A queued abort sits behind
   the very job it was sent to stop, because a consumer refuses to start
   a second job while one already owns the drivetrain.
3. **A full ring refuses and COUNTS.** Overwriting a slot still in
   flight makes a handler run a command nobody sent, silently.

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
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint]
    loaded.rbOffer.restype = ctypes.c_int
    loaded.rbOfferText.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
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
    for name in ("rbSlots", "rbTextBytes", "rbDedupe",
                 "rbOfferCodeMalformed", "rbOfferCodeSuppressed",
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

    def offer(self, text, now):
        """`text` may be bytes (raw payload, sent verbatim) or str."""
        if isinstance(text, str):
            text = text.encode()
        return self._l.rbOffer(self.h, text, len(text), now)

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
        "suppressed": lib.rbOfferCodeSuppressed(),
        "bypass": lib.rbOfferCodeBypass(),
        "queued": lib.rbOfferCodeQueued(),
        "dropped": lib.rbOfferCodeDropped(),
    }


# ---------------------------------------------------------------------------
# offer() / dispatchOne() / currentText(): the ordinary path
# ---------------------------------------------------------------------------


def test_a_parked_payload_comes_back_out_of_dispatch_one(lib, codes):
    with Bridge(lib) as b:
        assert b.offer("pivot:180", 1000) == codes["queued"]
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
        for i, text in enumerate(("square:60", "pivot:90", "straight:20")):
            assert b.offer(text, 1000 + 500 * i) == codes["queued"]
        seen = []
        while b.dispatch_one():
            seen.append(b.current())
        assert seen == ["square:60", "pivot:90", "straight:20"]


def test_a_trailing_carriage_return_is_stripped(lib, codes):
    """A raw terminal sends CRLF; the payload is the same command."""
    with Bridge(lib) as b:
        assert b.offer(b"pivot:90\r", 1000) == codes["queued"]
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
        assert b.offer(payload, 1000) == codes["malformed"]
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
        assert b.offer(payload, 1000) == codes["malformed"], shape
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
        for i, payload in enumerate((b"y" * 60, b"\x7f", b":a", b"")):
            assert b.offer(payload, 1000 + i) == codes["malformed"]
        assert b.malformed() == 4


def test_accepted_and_suppressed_payloads_leave_the_counter_alone(lib, codes):
    """A counter that also moved on ordinary traffic would be useless as
    a "something is wrong" signal."""
    with Bridge(lib) as b:
        assert b.offer("pivot:90", 1000) == codes["queued"]
        assert b.offer("pivot:90", 1001) == codes["suppressed"]
        assert b.offer("abort", 1002) == codes["bypass"]
        assert b.malformed() == 0


# ---------------------------------------------------------------------------
# The dedupe window
# ---------------------------------------------------------------------------


def test_a_repeat_just_inside_the_window_is_suppressed(lib, codes):
    window = lib.rbDedupe()
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        assert b.offer("tour:1", 1000 + window - 1) == codes["suppressed"]
        assert b.queued() == 1, (
            "the retransmit was parked as a second job -- the host's own "
            "duplicate would run the tour twice"
        )


def test_a_repeat_just_outside_the_window_is_accepted(lib, codes):
    """A deliberate re-run only has to be spaced past the window. A
    sweep that sends the same command twice in a row must not lose the
    second copy."""
    window = lib.rbDedupe()
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        assert b.offer("tour:1", 1000 + window) == codes["queued"]
        assert b.queued() == 2


def test_suppression_extends_the_window_across_a_burst(lib, codes):
    """Each suppressed copy restarts the clock, so a burst spaced closer
    than the window is swallowed whole however long it runs -- the
    burst, not its first copy, is what the window has to outlast."""
    window = lib.rbDedupe()
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        stamp = 1000
        for _ in range(5):
            stamp += window - 100
            assert b.offer("tour:1", stamp) == codes["suppressed"]
        assert b.queued() == 1
        # Total elapsed is now well past one window, yet nothing extra
        # was parked.
        assert stamp - 1000 > window


def test_different_text_inside_the_window_is_not_a_repeat(lib, codes):
    """Two commands differing only in their arguments are different
    text, so neither suppresses the other."""
    with Bridge(lib) as b:
        assert b.offer("pivot:180", 1000) == codes["queued"]
        assert b.offer("pivot:-180", 1010) == codes["queued"]
        assert b.queued() == 2


def test_dedupe_is_applied_at_arrival_not_at_handling(lib, codes):
    """The property that makes the window mean something: suppression
    compares arrival times, so a payload sitting in the ring behind a
    long job does not widen (or narrow) the window for the next
    arrival."""
    window = lib.rbDedupe()
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        # Nothing is ever dispatched here -- the payload stays parked --
        # and the window still expires on schedule.
        assert b.offer("tour:1", 1000 + window - 1) == codes["suppressed"]
        assert b.offer("tour:1", 1000 + 2 * window) == codes["queued"]
        assert b.queued() == 2


def test_only_the_most_recent_accepted_payload_is_compared(lib, codes):
    """Documented scope of the suppression: it catches a host's own
    back-to-back retransmits, not a command repeated after a different
    one has been accepted in between."""
    with Bridge(lib) as b:
        assert b.offer("pivot:90", 1000) == codes["queued"]
        assert b.offer("straight:20", 1010) == codes["queued"]
        assert b.offer("pivot:90", 1020) == codes["queued"]
        assert b.queued() == 3


# ---------------------------------------------------------------------------
# The abort / clearestop bypass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["abort", "clearestop"])
def test_the_bypass_names_skip_the_queue_and_are_staged_immediately(
        lib, codes, name):
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        assert b.offer(name, 1010) == codes["bypass"]
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
        assert b.offer("abort:now", 1000) == codes["bypass"]
        assert b.current() == "abort:now", (
            "the WHOLE payload is staged; only the match is name-only"
        )


@pytest.mark.parametrize("payload", ["abortive", "ab", "clearestops",
                                     "tour:abort"])
def test_names_that_merely_resemble_the_bypass_are_queued(lib, codes, payload):
    with Bridge(lib) as b:
        assert b.offer(payload, 1000) == codes["queued"]
        assert b.queued() == 1


def test_is_bypass_name_is_callable_without_an_instance(lib):
    """The rule is a property of the vocabulary, not of any one
    bridge's state -- a consumer can ask it directly."""
    assert lib.rbIsBypassName(b"abort") == 1
    assert lib.rbIsBypassName(b"clearestop:1") == 1
    assert lib.rbIsBypassName(b"pivot:90") == 0


def test_a_bypass_does_not_disturb_what_is_already_parked(lib, codes):
    with Bridge(lib) as b:
        assert b.offer("square:60", 1000) == codes["queued"]
        assert b.offer("abort", 1010) == codes["bypass"]
        assert b.dispatch_one() is True
        assert b.current() == "square:60", (
            "the bypass consumed a queued slot -- it must not dequeue"
        )
        assert b.dispatch_one() is False


def test_a_repeated_bypass_inside_the_window_still_executes(lib, codes):
    """The bypass names are EXEMPT from the dedupe window.

    The window's job is to stop a host's own retransmit executing
    twice. An operator hammering `abort` is not retransmitting -- and
    the entire reason these two names skip the queue is that nothing
    may stand between them and the drivetrain, which a suppression
    window did. It ate the second `abort` of a doubled press.

    Safe because both bypass handlers are idempotent (stop what is
    running; clear a latch that may already be clear) -- the same
    property that made them safe to invoke reentrantly from inside a
    running job."""
    with Bridge(lib) as b:
        assert b.offer("abort", 1000) == codes["bypass"]
        assert b.offer("abort", 1001) == codes["bypass"], (
            "a repeated abort inside the window must still execute"
        )
        assert b.offer("abort", 1002) == codes["bypass"]
        assert b.offer("clearestop", 1003) == codes["bypass"]
        assert b.offer("clearestop", 1004) == codes["bypass"]
        assert b.queued() == 0, "a bypass never parks"


def test_the_bypass_exemption_does_not_leak_to_ordinary_names(lib, codes):
    """Exempting the bypass names must not disturb suppression for
    anything else -- including a name that merely starts with one of
    them."""
    with Bridge(lib) as b:
        assert b.offer("abortive:1", 1000) == codes["queued"]
        assert b.offer("abortive:1", 1001) == codes["suppressed"]


def test_a_bypass_between_two_repeats_resets_the_compared_text(lib, codes):
    """The bypass path still records itself as the last accepted text
    (it takes the same `lastText_` update every accepted payload does),
    so a repeat that straddles one is no longer a repeat of anything.
    Pinned as observed behavior rather than argued for: it is what
    "suppression compares against the MOST RECENT accepted payload"
    already means."""
    with Bridge(lib) as b:
        assert b.offer("tour:1", 1000) == codes["queued"]
        assert b.offer("abort", 1001) == codes["bypass"]
        assert b.offer("tour:1", 1002) == codes["queued"]


# ---------------------------------------------------------------------------
# Ring overflow
# ---------------------------------------------------------------------------


def test_a_full_ring_refuses_and_counts(lib, codes):
    slots = lib.rbSlots()
    with Bridge(lib) as b:
        for i in range(slots):
            assert b.offer(f"cmd:{i}", 1000 + 1000 * i) == codes["queued"]
        assert b.queued() == slots
        assert b.dropped() == 0
        assert b.offer("one-too-many", 100000) == codes["dropped"], (
            "a full ring must refuse, not overwrite a slot still in flight"
        )
        assert b.dropped() == 1
        assert b.offer("and-another", 200000) == codes["dropped"]
        assert b.dropped() == 2
        # The payloads that WERE accepted are all still intact and in
        # order -- that is what the refusal buys.
        assert b.dispatch_one() and b.current() == "cmd:0"
        assert b.offer("now-fits", 300000) == codes["queued"]


def test_a_dropped_payload_still_counts_as_the_last_accepted_text(lib, codes):
    """Dedupe runs BEFORE the ring is consulted, so a dropped payload
    has already updated the suppression state. Pinned as observed
    behavior: an immediate retransmit of the dropped command is
    suppressed rather than retried into a ring that is still full."""
    slots = lib.rbSlots()
    with Bridge(lib) as b:
        for i in range(slots):
            assert b.offer(f"cmd:{i}", 1000 + 1000 * i) == codes["queued"]
        assert b.offer("overflowing", 100000) == codes["dropped"]
        assert b.offer("overflowing", 100001) == codes["suppressed"]
        assert b.dropped() == 1


# ---------------------------------------------------------------------------
# Sizing constants
# ---------------------------------------------------------------------------


def test_the_ring_matches_the_slot_and_payload_sizing_it_replaced(lib):
    """RunBridge's ring is run_queue.h's, at the same 8 x 48 sizing the
    inline version used -- a payload that fit before must still fit."""
    assert lib.rbSlots() == 8
    assert lib.rbTextBytes() == 48
    assert lib.rbDedupe() == 400
