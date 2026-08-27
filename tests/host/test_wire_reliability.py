"""tests/host/test_wire_reliability.py -- protocol v6's reliability
layer for src/wire_handler.{h,cpp}: the
mandatory, trailing, digits-only `#<n>` sequence id; handler state
limited to exactly `expectedNext_`/`gapOutstanding_` (no clock, no
timer); the three-way classification of every inbound id; and
decode-failure-is-NAK, distinguished sharply from a merits rejection.

This file does NOT re-test wire grammar mechanics (line reassembly,
tokenizing, case-as-direction) or the nine verbs' own golden vectors --
both live in test_wire_grammar.py, whose `wire_lib` fixture, `wg`
fixture, `WireGrammar` wrapper, and RESULT_*/DONE_*/TLM_* constants this
file reuses directly (one compiled shared library, one binding table,
per radio-robot-lib/tests/protocol's own "one shim, several pytest
files" pattern -- see wire_grammar_shim.cpp's own file header).

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S8.1 (the three-way table --
the core of this file), S8.3 (the unsequenced exemption set and HELLO's
own reset), S8.5 (periodic emission piggybacked on telemetry, still no
timer), S8.6 (err's field order), S8.8 (lastDone/lastDoneReason moved to
the Adapter), S8.9 (decode failure is a NAK -- the central 2026-08-22
change, and the reason this file exists).

Run with::

    uv run pytest tests/host/test_wire_reliability.py
"""

import pytest

from test_wire_grammar import (  # noqa: F401 -- wg/wire_lib re-exported as fixtures
    DONE_ABORTED,
    DONE_ESTOP,
    DONE_STOP,
    DONE_TIMEOUT,
    RESULT_OK,
    RESULT_RANGE,
    _ack,
    _nack,
    wg,
    wire_lib,
)

# ---------------------------------------------------------------------------
# Mandatory id: missing or malformed -- cannot be sequence-classified at
# all, so there is no reply of any kind (protocol.md S8.4 items 1-2).
# The id grammar is digits-only and unsigned -- stricter than the
# general signed-integer field parser (S2.2) -- so a dedicated parser is
# required, not the general one.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        b"STOP\n",  # no trailing field at all
        b"STOP #\n",  # bare hash, no digits
        b"STOP #+5\n",  # signed -- '+' is not a digit
        b"STOP #-5\n",  # signed -- '-' is not a digit
        b"STOP # 5\n",  # the space splits this into two tokens; the
                           # real last token is "5", which doesn't even
                           # start with '#'
        b"STOP #5a\n",  # trailing non-digit content
    ],
)
def test_malformed_or_missing_id_on_sequenced_verb_nacks(wg, line):
    """2026-08-27, stakeholder direction. These used to be answered with
    TOTAL SILENCE. From the operator's seat that is indistinguishable
    from a dead robot, a dropped packet, an unknown verb or a wedged
    link -- "if I don't put a number on something, there should be an
    error... where's my NAK, or my error, or ANYTHING that tells me
    what happened?"

    `nack <expectedNext_>` is exactly the right answer: "I did not run
    that; send me id N." The verb still does not execute and the
    sequence does not move."""
    wg.feed(line)
    assert wg.take_sink() == _nack(1)
    assert wg.malformed_count == 1
    assert wg.stop_calls == 0


def test_missing_id_nack_does_not_move_the_sequence(wg):
    """A missing id is a malformed LINE, not evidence that a numbered
    command was lost -- so expectedNext_ must not move and #1 must still
    be accepted immediately afterwards."""
    wg.feed(b"STOP\n")
    assert wg.take_sink() == _nack(1)
    wg.feed(b"STOP #1\n")
    assert wg.take_sink() == _ack(1)


def test_missing_id_nack_does_not_raise_the_stall_reminder(wg):
    """gapOutstanding_ must stay false: nothing was lost, the operator
    just forgot an id. Otherwise every later query would nag about a
    stall that never happened."""
    wg.feed(b"STOP\n")
    wg.take_sink()
    wg.feed(b"ID\n")
    out = wg.take_sink()
    assert out.startswith(b"id ")
    assert b"nack" not in out, out


@pytest.mark.parametrize("line", [b"NOTAVERB\n", b"BOGUS 1 2 3\n",
                                   b"XYZZY #\n"])
def test_unrecognized_verb_without_an_id_stays_silent(wg, line):
    """Deliberately NOT nacked. The radio channel is shared: answering
    arbitrary uppercase garbage would make this robot chatter at every
    corrupted line and at other robots' traffic that survives the case
    gate. A verb this handler implements is addressed to it; an unknown
    token is not assumed to be."""
    wg.feed(line)
    assert wg.take_sink() == b""
    assert wg.malformed_count == 1


def test_well_formed_id_with_many_digits_is_accepted(wg):
    """The digits-only parser accepts an ordinary multi-digit id -- this
    is the well-formed baseline the malformed-shapes test above is
    contrasted against."""
    wg.feed(b"STOP #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.malformed_count == 0


# ---------------------------------------------------------------------------
# The three-way classification (protocol.md S8.1). The middle row is the
# one this ticket calls out by name: a resent command whose ack was lost
# must NOT re-invoke the adapter.
# ---------------------------------------------------------------------------


def test_in_order_id_decodes_dispatches_and_advances(wg):
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 3.5 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1
    # The sequence genuinely advanced: #2 is now in-order.
    wg.feed(b"SET group.alpha 4.5 #2\n")
    assert wg.take_sink() == _ack(2)
    assert wg.set_calls == 2


def test_stale_retransmit_reacks_already_accepted_id_and_does_not_reexecute(wg):
    """The core test this ticket calls out by name: a resent command
    whose ack was lost must NOT drive the adapter a second time. Reply
    echoes the ALREADY-accepted id (expectedNext_ - 1), not the resent
    one."""
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 3.5 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1

    # The host never saw that ack and resends the SAME line, same id.
    wg.feed(b"SET group.alpha 3.5 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1, "a stale retransmit must not re-invoke the adapter"
    assert wg.malformed_count == 0


def test_hash_zero_is_rejected_not_treated_as_a_stale_retransmit(wg):
    """SUPERSEDES the S2.2 reading that `#0` needs no special case.

    That reading was true of the mechanism -- #0 IS always below
    expectedNext_ -- but the resulting reply was indefensible: `ack
    <expectedNext_ - 1>`, which on a fresh session is `ack 0 0 none`. A
    receipt for a command that never existed and never ran. Reported
    from the field on a motion verb, where the robot correspondingly did
    not move.

    #0 is now REJECTED as the malformed id it is: nack, no execution, no
    sequence movement, counted malformed."""
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 3.5 #0\n")
    assert wg.take_sink() == _nack(1)
    assert wg.set_calls == 0
    assert wg.malformed_count == 1


def test_numeric_gap_nacks_and_does_not_execute(wg):
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 3.5 #5\n")
    assert wg.take_sink() == _nack(1)
    assert wg.set_calls == 0


def test_numeric_gap_does_not_increment_malformed_count(wg):
    """A numeric gap is a normal, expected occurrence on a lossy/
    reordering transport, not a protocol violation -- its content is
    never even inspected, so it must never count malformed."""
    wg.feed(b"SET group.alpha 3.5 #5\n")
    assert wg.malformed_count == 0
    wg.feed(b"TOTALLY_BOGUS_VERB #99\n")
    assert wg.malformed_count == 0, (
        "an out-of-order line's content, verb included, is never inspected")


# ---------------------------------------------------------------------------
# Decode-failure-is-NAK (protocol.md S8.9), distinguished sharply from a
# merits rejection. Both emit `err`; only the merits case advances.
# ---------------------------------------------------------------------------


def test_unrecognized_verb_in_order_is_a_decode_failure_nacks_same_id(wg):
    wg.feed(b"TOTALLY_BOGUS_VERB #1\n")
    assert wg.take_sink() == _nack(1) + b"err 1 #1\n"
    assert wg.malformed_count == 1


def test_wrong_arity_known_verb_in_order_is_a_decode_failure(wg):
    """STOP takes zero data fields -- an extra one is wrong arity, a
    decode failure (err 2 ERR_BADARG), not a best-effort parse."""
    wg.feed(b"STOP extra #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.malformed_count == 1
    assert wg.stop_calls == 0


def test_unparseable_field_is_a_decode_failure(wg):
    """SET's value field must parse as a float -- "notanumber" does
    not, so this NACKs rather than reaching the adapter at all."""
    wg.feed(b"SET group.alpha notanumber #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.set_calls == 0


def test_unrecognized_tlm_mode_is_a_decode_failure(wg):
    wg.feed(b"TLM BOGUS #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.tlm_calls == 0


def test_stop_trailing_token_other_than_now_is_a_decode_failure(wg):
    wg.feed(b"STOP later #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.stop_calls == 0


def test_run_with_only_the_id_and_no_function_name_is_a_decode_failure(wg):
    """Resolves an internal inconsistency in protocol.md: S6.3's own RUN
    table still reads "RUN #7 -- still ack + err 2", but S8.9 explicitly
    lists "a bare RUN with no function name" among its OWN decode-failure
    examples, and the reference implementation (protocol_handler.cpp)
    nacks this case, not acks. S8.9 is the later, central, explicitly-
    authoritative section (2026-08-22) -- implemented here to match it
    and the reference behavior, not S6.3's stale table row."""
    wg.feed(b"RUN #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.run_calls == 0


def test_decode_failure_holds_the_sequence_until_a_well_formed_line_arrives(wg):
    """A decode failure on an in-order id holds the stream exactly like
    a numeric gap: it keeps re-nacking the SAME id until a well-formed
    line finally supplies it -- proving the state truly did not move."""
    wg.feed(b"SET group.alpha notanumber #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.malformed_count == 1

    # Still #1 -- a second, different malformed line at the same id
    # nacks identically.
    wg.feed(b"TLM BOGUS #1\n")
    assert wg.take_sink() == _nack(1) + b"err 2 #1\n"
    assert wg.malformed_count == 2

    # Finally, a well-formed line carrying the SAME id advances it.
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 1.0 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1


def test_merits_rejection_acks_and_advances_unlike_a_decode_failure(wg):
    """A merits rejection -- decoded fine, refused by the ADAPTER on its
    own terms -- is the opposite of a decode failure: it ACKS (the
    sequence advances) and is paired with err on top of that ack."""
    wg.set_set_result(RESULT_RANGE)
    wg.feed(b"SET group.alpha 99999 #1\n")
    assert wg.take_sink() == _ack(1) + b"err 3 #1\n"
    assert wg.set_calls == 1, "a merits rejection still reaches the adapter"

    # The sequence genuinely advanced -- #1 is now stale, and resending
    # it re-acks WITHOUT invoking the adapter a second time (resending a
    # merits-rejected line would just be refused again, identically, so
    # this case advances and moves on rather than holding the stream).
    wg.feed(b"SET group.alpha 99999 #1\n")
    assert wg.take_sink() == _ack(1)
    assert wg.set_calls == 1


# ---------------------------------------------------------------------------
# Gap stalling and self-healing (protocol.md S8.1; 2026-08-26 S8.5):
# once a gap opens, every subsequent well-formed command is nacked
# identically until the missing id arrives -- and that per-inbound-line
# repeat is the ONLY re-nack there is. emitReliability() (the old
# keepalive) is deleted: an ack/nack is only ever a direct reply to an
# inbound line, never a beacon; a lost nack self-heals because the
# host's own next line (command or retransmit) provokes a fresh one.
# ---------------------------------------------------------------------------


def test_gap_stalls_every_subsequent_command_identically(wg):
    wg.feed(b"SET group.alpha 1.0 #5\n")
    assert wg.take_sink() == _nack(1)

    # A DIFFERENT, otherwise-well-formed command, still out of order,
    # nacks identically -- the missing id, not the command just sent.
    wg.feed(b"STOP #6\n")
    assert wg.take_sink() == _nack(1)
    assert wg.set_calls == 0
    assert wg.stop_calls == 0
    assert wg.malformed_count == 0


def test_missing_id_finally_arriving_resumes_the_sequence(wg):
    wg.feed(b"SET group.alpha 1.0 #5\n")
    wg.take_sink()

    wg.feed(b"STOP #1\n")
    assert wg.take_sink() == _ack(1)
    wg.set_set_result(RESULT_OK)
    wg.feed(b"SET group.alpha 1.0 #2\n")
    assert wg.take_sink() == _ack(2)
    assert wg.set_calls == 1


def test_lost_nack_self_heals_via_the_hosts_own_next_line(wg):
    """The scheme's self-healing guarantee, post-piggyback (2026-08-26,
    S8.5): a lost nack is recovered by the host's own NEXT inbound line
    -- a retransmit of the missing id, or any further command -- which
    provokes a fresh, identical nack. Nothing fires with no inbound
    line at all: the wire stays silent."""
    wg.feed(b"SET group.alpha 1.0 #5\n")
    wg.take_sink()  # the original nack is "lost" -- simply discarded

    wg.feed(b"SET group.alpha 1.0 #6\n")
    assert wg.take_sink() == _nack(1)

    # It keeps happening on every subsequent inbound line, not just once.
    wg.feed(b"STOP #7\n")
    assert wg.take_sink() == _nack(1)


def test_lost_ack_self_heals_via_the_hosts_own_retransmit(wg):
    """The lost-ack half (S8.1's stale-retransmit row): a host that
    never saw its ack resends the same id; the handler re-acks WITHOUT
    re-executing. This replaces the deleted emitReliability() re-ack --
    the host's own retransmit, not a firmware beacon, is the heal."""
    wg.feed(b"STOP #1\n")
    wg.take_sink()  # the ack is "lost" -- simply discarded
    stop_calls_after_first = wg.stop_calls

    wg.feed(b"STOP #1\n")  # host retransmit of the same id
    assert wg.take_sink() == _ack(1), (
        "a stale retransmit gets the bare re-ack alone -- no status "
        "line, since the verb is never re-executed")
    assert wg.stop_calls == stop_calls_after_first, (
        "a stale retransmit must re-ack, never re-execute")


# ---------------------------------------------------------------------------
# HELLO resets the sequence (protocol.md S8.3) but does NOT touch the
# Adapter's own lastDone()/lastDoneReason() (S8.8).
# ---------------------------------------------------------------------------


def test_hello_resets_expected_next_after_a_gap(wg):
    wg.feed(b"SET group.alpha 1.0 #5\n")  # opens a gap; expectedNext_ stays 1
    wg.take_sink()

    wg.feed(b"HELLO\n")
    wg.take_sink()  # the banner; not under test here

    # expectedNext_ is back to 1 -- #1 is in-order again, and the gap is
    # cleared (no more nacking).
    wg.feed(b"STOP #1\n")
    text = wg.take_sink()
    assert text.startswith(_ack(1))
    # STATUS is unsequenced (2026-08-27), so probing expectedNext_ here
    # cannot itself consume an id and perturb what is under test.
    wg.feed(b"STATUS\n")
    assert b"next=2" in wg.take_sink()


def test_hello_does_not_touch_adapters_last_done(wg):
    wg.set_last_done(7, DONE_STOP)
    wg.feed(b"HELLO\n")
    wg.take_sink()

    wg.feed(b"STOP #1\n")
    assert wg.take_sink().startswith(_ack(1, 7, DONE_STOP))


# ---------------------------------------------------------------------------
# lastDone/reason piggyback fresh onto every ack/nack (protocol.md S8.8)
# -- polled off the Adapter each time, never cached on the handler.
# ---------------------------------------------------------------------------


def test_ack_carries_the_adapters_current_last_done_and_reason(wg):
    wg.set_last_done(3, DONE_TIMEOUT)
    wg.feed(b"STOP #1\n")
    assert wg.take_sink().startswith(_ack(1, 3, DONE_TIMEOUT))


def test_nack_carries_the_adapters_current_last_done_and_reason(wg):
    wg.set_last_done(9, DONE_ESTOP)
    wg.feed(b"SET group.alpha 1.0 #5\n")  # a numeric gap
    assert wg.take_sink() == _nack(1, 9, DONE_ESTOP)


def test_last_done_is_read_fresh_not_cached_across_calls(wg):
    """Changing the adapter's own lastDone() between two calls changes
    what the NEXT ack reports -- proving there is no cached copy
    anywhere on WireHandler."""
    wg.set_last_done(1, DONE_STOP)
    wg.feed(b"STOP #1\n")
    assert wg.take_sink().startswith(_ack(1, 1, DONE_STOP))

    wg.set_last_done(2, DONE_ABORTED)
    wg.feed(b"STOP #2\n")
    assert wg.take_sink().startswith(_ack(2, 2, DONE_ABORTED))


# ---------------------------------------------------------------------------
# err's field order (protocol.md S8.6): code first, id last -- not the
# other way around.
# ---------------------------------------------------------------------------


def test_err_field_order_is_code_then_hash_id(wg):
    wg.set_set_result(RESULT_RANGE)
    wg.feed(b"SET group.alpha 99999 #1\n")
    sink = wg.take_sink()
    assert b"err 3 #1\n" in sink
    assert b"err #1 3\n" not in sink


# ---------------------------------------------------------------------------
# `#0` -- never a legal id (2026-08-27)
# ---------------------------------------------------------------------------


def test_id_zero_nacks_rather_than_acking_a_command_that_never_ran(wg):
    """Reported from the field: `WHEELS_X 100 100 1000 #0` answered
    `ack 0 0 none` and the robot did not move. Ids start at 1, so #0 is
    never legal -- it used to land in the stale-retransmit bucket and be
    acked against expectedNext_ - 1, which on a fresh session IS zero.
    A receipt for a command that never existed."""
    wg.feed(b"WHEELS_V 100 100 #0\n")
    assert wg.take_sink() == _nack(1)
    assert wg.malformed_count == 1


def test_id_zero_does_not_move_the_sequence_or_stall_it(wg):
    wg.feed(b"STOP #0\n")
    assert wg.take_sink() == _nack(1)
    wg.feed(b"STOP #1\n")            # #1 still next
    assert wg.take_sink() == _ack(1)
    wg.feed(b"ID\n")                 # and no stall reminder was raised
    out = wg.take_sink()
    assert out.startswith(b"id ") and b"nack" not in out, out


def test_unsequenced_verbs_still_answer_after_an_id_zero_line(wg):
    """The field report showed ID and HELP going silent right after a
    `#0` line. Pins that a rejected id cannot wedge the unsequenced
    plane."""
    wg.feed(b"WHEELS_V 100 100 #0\n")
    wg.take_sink()
    for verb, prefix in ((b"ID", b"id "), (b"HELP", b"help "),
                          (b"PING", b"pong"), (b"VER", b"ver ")):
        wg.feed(verb + b"\n")
        assert wg.take_sink().startswith(prefix), verb
