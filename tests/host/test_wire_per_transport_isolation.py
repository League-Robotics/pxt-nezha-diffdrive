"""tests/host/test_wire_per_transport_isolation.py -- proves the
structural property sprint 004 ticket 001 is entirely built on top of
(wifi-link.md:373's "a separate ProtocolHandler per transport over one
shared adapter"; sprint.md's SUC-002): two independent
Wire::WireHandler instances never share expectedNext_/gapOutstanding_/
malformedCount_ state, so a sequence gap opened on ONE handler leaves
the OTHER's ack stream and malformed count completely unaffected.

Ticket 001 wires src/protocol.h's wireHandler_ (serial) and the new
wireHandlerRadio_ (radio) as two such instances, composed over the SAME
WireAdapter instance (see protocol.h's own comment on that member
pair) -- but Protocol itself is CODAL-bound and has no host shim (it
`#include`s pxt.h transitively through platform_ports.h), so that
specific pair can only be verified by code review, per this ticket's
own testing plan. What IS host-testable, and is this file's whole job,
is the underlying CLASS property those two production instances rely
on: two `Wire::WireHandler`s, however they are composed in production,
never cross-contaminate each other's reliability state. Proving that
here, once, is what makes relying on it in protocol.h safe.

No new C++ and no new shim function were needed: wgCreate()
(wire_grammar_shim.cpp) already returns an independent Handle (its own
WireMockAdapter + RecordingSink + WireHandler bundle) on every call,
and expectedNext_/gapOutstanding_/malformedCount_ are already plain
WireHandler instance members (wire_handler.h) -- never shared or
static. This file just drives two handles at once and asserts what
was already true of the class.

Reuses test_wire_grammar.py's `wire_lib` fixture and `WireGrammar`
wrapper directly rather than duplicating the ctypes binding table --
this project's own "one shim, several pytest files" convention (see
wire_grammar_shim.cpp's own file header, and test_wire_reliability.py's
identical reuse).

Run with::

    uv run pytest tests/host/test_wire_per_transport_isolation.py
"""

from test_wire_grammar import (  # noqa: F401 -- wire_lib re-exported as a fixture
    RESULT_OK,
    WireGrammar,
    _ack,
    _nack,
    wire_lib,
)

# ---------------------------------------------------------------------------
# SUC-002's own acceptance criteria: a gap on one handler must not nack
# the other's next command, and must not affect its malformedCount()
# either.
# ---------------------------------------------------------------------------


def test_sequence_gap_on_one_handler_does_not_disturb_the_others_acks(wire_lib):
    """The core property SUC-002 requires: a radio host's own gap must
    never disturb a serial host's in-order traffic, or vice versa --
    modeled here as two independent handles rather than naming either
    one "serial" or "radio" (the property is transport-agnostic; only
    Protocol's own composition -- not host-testable -- decides which
    physical transport each handler ends up wired to)."""
    with WireGrammar(wire_lib) as a, WireGrammar(wire_lib) as b:
        # Handle A's very first command arrives as #5 -- a numeric gap
        # from a fresh handler's expectedNext_ == 1 -- and nacks.
        a.feed(b"STATUS #5\n")
        assert a.take_sink() == _nack(1)

        # Handle B, fed a normal in-order sequence, acks exactly as a
        # fresh, never-gapped handler would -- A's gap left no trace.
        b.feed(b"STATUS #1\n")
        assert b.take_sink().startswith(_ack(1))

        b.set_set_result(RESULT_OK)
        b.feed(b"SET group.alpha 1.0 #2\n")
        assert b.take_sink() == _ack(2)
        assert b.set_calls == 1


def test_malformed_count_is_isolated_between_handlers(wire_lib):
    """malformedCount() is a plain instance member (wire_handler.h) --
    a decode failure on one handle must not tick the other's counter."""
    with WireGrammar(wire_lib) as a, WireGrammar(wire_lib) as b:
        # A decode failure (protocol.md S8.9) on A increments ONLY A's
        # own count.
        a.feed(b"TOTALLY_BOGUS_VERB #1\n")
        assert a.malformed_count == 1

        assert b.malformed_count == 0
        b.feed(b"STATUS #1\n")
        assert b.malformed_count == 0


def test_a_handlers_open_gap_keeps_stalling_only_that_handler(wire_lib):
    """Extends the first test across several commands, not just the
    one instant they happen to overlap: A's gap doesn't just fail to
    disturb a single command on B -- it never disturbs ANY of B's
    subsequent traffic, and stays open on A the whole time, unaffected
    by B's unrelated activity."""
    with WireGrammar(wire_lib) as a, WireGrammar(wire_lib) as b:
        a.feed(b"STATUS #5\n")
        a.take_sink()  # the initial nack; not under test here

        # Drive B through three in-order commands; each acks normally,
        # oblivious to A's still-open gap.
        b.set_set_result(RESULT_OK)
        for i in range(1, 4):
            b.feed("SET group.alpha 1.0 #{}\n".format(i).encode())
            assert b.take_sink() == _ack(i)
        assert b.set_calls == 3

        # A's gap is still open, unaffected by B's unrelated traffic --
        # a DIFFERENT command, still #5 (the same missing id), nacks
        # identically rather than having somehow resumed.
        a.feed(b"STATUS #5\n")
        assert a.take_sink() == _nack(1)
        assert a.status_calls == 0
