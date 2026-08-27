"""tests/host/test_wire_telemetry_frame.py -- protocol v6's telemetry
frame (`radio-robot-lib/docs/design/protocol.md` S5.2: `thdr <col>...`
then `t <v>...`, space-separated, lowercase, unsequenced -- no `#id`)
for src/wire_handler.{h,cpp} (sprint 004 ticket 003).

This ticket is PURE FORMATTING: it takes a caller-supplied
`Wire::Column`/`Wire::Snapshot` (copied from the reference's shape,
radio-robot-lib/src/protocol/adapter.h:113-139) and prints it -- it has
no opinion on what a column MEANS or where its value came from. Every
test below hand-builds its own `Column` array; none of them touch
`WireAdapter` or any robot state (that projection is ticket 004's
separate scope -- see sprint.md's Phase B narrative and Design
Rationale for why the split is deliberate: this ticket's own bugs are
formatting/ordering bugs, not unit-scale bugs).

Reuses test_wire_grammar.py's `wire_lib` fixture, `wg` fixture,
`WireGrammar` wrapper (widened this ticket with `emit_telemetry()`/
`take_sink_writes()`; `emit_reliability()` was deleted 2026-08-26 along
with the telemetry ack piggyback, S8.5), and `_ack`/`_nack` helpers,
per this project's own "one shim, several pytest files" convention
(wire_grammar_shim.cpp's own file header).

Run with::

    uv run pytest tests/host/test_wire_telemetry_frame.py
"""

import ctypes

from test_wire_grammar import (  # noqa: F401 -- wg/wire_lib re-exported as fixtures
    _ack,
    _nack,
    wg,
    wire_lib,
)

# ---------------------------------------------------------------------------
# thdr due on frame 1; not due on frame 2 with an unchanged column set
# (sprint.md SUC-003's own main flow).
# ---------------------------------------------------------------------------


def test_first_frame_emits_thdr_then_t_and_nothing_else(wg):
    columns = [(b"x", 10, False), (b"y", -5, False), (b"flags", 0x2A, True)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"thdr x y flags\n", b"t 10 -5 2a\n"]


def test_second_frame_with_unchanged_columns_emits_only_t(wg):
    columns = [(b"x", 10, False), (b"y", -5, False), (b"flags", 0x2A, True)]
    wg.emit_telemetry(columns)
    wg.take_sink_writes()  # frame 1's thdr/t -- not under test here

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"t 10 -5 2a\n"]


# ---------------------------------------------------------------------------
# Byte-exact ordering: thdr -> t, as SEPARATE Sink::write() calls --
# asserted on the RecordingSink's own per-call log (take_sink_writes()),
# not just the concatenated buffer. NO reliability line rides along
# (2026-08-26, protocol.md S8.5: the telemetry ack piggyback is DELETED
# -- an ack/nack is only ever a direct reply to an inbound line).
# ---------------------------------------------------------------------------


def test_emit_telemetry_writes_exactly_two_separate_lines_when_thdr_due(wg):
    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert len(writes) == 2
    assert writes[0] == b"thdr a\n"
    assert writes[1] == b"t 1\n"


def test_emit_telemetry_writes_exactly_one_line_when_thdr_not_due(wg):
    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    wg.take_sink_writes()

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"t 1\n"]


def test_emit_telemetry_stays_silent_on_reliability_even_with_a_gap(wg):
    """An outstanding gap must NOT leak onto the telemetry channel
    (2026-08-26, S8.5): the re-nack arrives on the next INBOUND line
    (S8.1), never on a frame."""
    wg.feed(b"SET group.alpha 1.0 #5\n")  # opens a gap: expectedNext_ stays 1
    wg.take_sink()  # the nack from feed() itself -- not under test here

    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"thdr a\n", b"t 1\n"]

    # The stalled stream still re-nacks -- per inbound line.
    wg.feed(b"SET group.alpha 1.0 #6\n")
    assert wg.take_sink_writes() == [_nack(1)]


# ---------------------------------------------------------------------------
# thdr re-emitted on ANY of: count change, name change, or a
# hex-ness-ONLY change (same names, same count) -- the lazy-memo trap
# the issue calls out explicitly: a memo comparing only names/count
# would miss the third case.
# ---------------------------------------------------------------------------


def test_thdr_re_emitted_on_column_count_change(wg):
    wg.emit_telemetry([(b"a", 1, False)])
    wg.take_sink_writes()

    wg.emit_telemetry([(b"a", 1, False), (b"b", 2, False)])
    writes = wg.take_sink_writes()
    assert writes[0] == b"thdr a b\n"


def test_thdr_re_emitted_on_column_name_change(wg):
    wg.emit_telemetry([(b"a", 1, False)])
    wg.take_sink_writes()

    wg.emit_telemetry([(b"z", 1, False)])
    writes = wg.take_sink_writes()
    assert writes[0] == b"thdr z\n"


def test_thdr_re_emitted_on_hex_ness_only_change(wg):
    """Same name, same count, ONLY the hex flag flips -- the exact trap
    named in the ticket: a memo keyed on names/count alone would treat
    this as unchanged and never resend thdr, silently breaking any
    consumer decoding by column position."""
    wg.emit_telemetry([(b"a", 10, False)])
    writes1 = wg.take_sink_writes()
    assert writes1[1] == b"t 10\n"

    wg.emit_telemetry([(b"a", 10, True)])
    writes2 = wg.take_sink_writes()
    assert writes2[0] == b"thdr a\n"
    assert writes2[1] == b"t a\n"  # now rendered as hex, no "0x" prefix


def test_thdr_not_re_emitted_when_nothing_changed_at_all(wg):
    """The negative-space control for the three tests above: with
    truly unchanged name/count/hex-ness, no thdr goes out on the second
    call."""
    wg.emit_telemetry([(b"a", 1, False), (b"b", 2, True)])
    wg.take_sink_writes()

    wg.emit_telemetry([(b"a", 3, False), (b"b", 4, True)])  # values may
                                                             # change freely
    writes = wg.take_sink_writes()
    assert writes[0] == b"t 3 4\n"


# ---------------------------------------------------------------------------
# The 20-frame (~1 Hz) forced refresh (sprint.md SUC-004): independent
# of whether the column set changed, a fresh thdr goes out at frame 20
# -- not merely "eventually", and not at frame 1 alone. Held constant
# for 25 frames total, per SUC-004's own acceptance criterion.
# ---------------------------------------------------------------------------


def test_thdr_forced_refresh_appears_at_frame_20_not_only_frame_1(wg):
    columns = [(b"x", 1, False), (b"y", 2, False)]

    wg.emit_telemetry(columns)  # frame 1
    assert wg.take_sink_writes()[0].startswith(b"thdr")

    thdr_frames = []
    for frame in range(2, 26):
        wg.emit_telemetry(columns)
        writes = wg.take_sink_writes()
        if writes[0].startswith(b"thdr"):
            thdr_frames.append(frame)

    assert thdr_frames == [20]


def test_thdr_forced_refresh_counter_resets_after_a_real_change(wg):
    """A real column-set change before frame 20 re-anchors the 20-frame
    counter -- the NEXT forced refresh is 20 frames after THAT thdr,
    not 20 frames after frame 1."""
    columns_a = [(b"x", 1, False)]
    columns_b = [(b"x", 1, False), (b"y", 2, False)]

    wg.emit_telemetry(columns_a)  # frame 1 -- thdr
    wg.take_sink_writes()

    for _ in range(4):  # frames 2-5, unchanged
        wg.emit_telemetry(columns_a)
        assert not wg.take_sink_writes()[0].startswith(b"thdr")

    wg.emit_telemetry(columns_b)  # frame 6 -- real change, re-anchors
    assert wg.take_sink_writes()[0].startswith(b"thdr")

    thdr_frames = []
    for frame in range(7, 27):  # frames 7..26
        wg.emit_telemetry(columns_b)
        writes = wg.take_sink_writes()
        if writes[0].startswith(b"thdr"):
            thdr_frames.append(frame)

    # Frame 6's thdr is the 1st frame of a new streak; the 20th frame
    # of THAT streak is frame 6 + 19 = 25 -- not frame 20 (which came
    # and went, uneventfully, before the change), and not frame 26.
    assert thdr_frames == [25]


# ---------------------------------------------------------------------------
# The header memo stores a COPY, not a borrowed pointer into the
# caller's own Snapshot: mutating the ORIGINAL backing storage's
# CONTENT after a thdr emission must not affect the NEXT
# headerChanged() check, which compares against the remembered copy.
# ---------------------------------------------------------------------------


def test_header_memo_stores_a_copy_not_a_borrowed_pointer(wg, wire_lib):
    name_buf = ctypes.create_string_buffer(b"x", 8)
    names = (ctypes.c_char_p * 1)(ctypes.cast(name_buf, ctypes.c_char_p))
    values = (ctypes.c_int32 * 1)(10)
    hex_flags = (ctypes.c_int * 1)(0)

    wire_lib.wgEmitTelemetry(wg._handle, names, values, hex_flags, 1)
    writes = wg.take_sink_writes()
    assert writes[0] == b"thdr x\n"

    # Mutate the ORIGINAL backing buffer's content IN PLACE, at the
    # SAME address, after the call that already remembered "x" has
    # returned. A memo that stored a bare pointer into this buffer
    # (instead of copying the name) would now see "y" when it next
    # reads through that pointer.
    name_buf.value = b"y"

    # A second, INDEPENDENTLY allocated snapshot whose column name is
    # "x" again -- matching what was REMEMBERED, not whatever the
    # first buffer's address now holds. A correct copy-based memo sees
    # "x" == "x" (unchanged, no thdr). A buggy pointer-based memo would
    # dereference the first buffer (now "y"), see "y" != "x", and
    # incorrectly re-emit thdr.
    name_buf2 = ctypes.create_string_buffer(b"x", 8)
    names2 = (ctypes.c_char_p * 1)(ctypes.cast(name_buf2, ctypes.c_char_p))
    wire_lib.wgEmitTelemetry(wg._handle, names2, values, hex_flags, 1)
    writes2 = wg.take_sink_writes()
    assert writes2[0].startswith(b"t ")  # NOT thdr


# ---------------------------------------------------------------------------
# Byte-width vs RadioTransport's TX truncation cap (sprint.md Open
# Question 2). This ticket is pure formatting with no real WireAdapter
# projection (that is ticket 004's separate scope, and ticket 004 owns
# the AUTHORITATIVE widest-real-FULL-set test against actual scaled
# robot values) -- these two tests instead measure this ticket's own
# formatting mechanism against a hand-built stand-in for the sprint's
# documented 20-column POSE+FULL set
# ("seq now flags x y h ox oy oh vl vr i2cf cyc posl posr dutl dutr
# lexc wrng cycovr"), so a concrete, test-pinned number exists before
# ticket 004 lands the real one.
#
# RadioTransport::kMaxPayloadBytes was 200 when these two tests were
# first written (sprint 004 ticket 003); sprint 010 ticket 002 raised
# it to 240 (radio-rx-capacity-fragmentation.md), closing the gap with
# the wire grammar's own 240-byte line ceiling. The boundary values
# below are updated to that new cap -- see each test's own docstring
# for what changed.
# ---------------------------------------------------------------------------

_FULL_COLUMN_NAMES = [
    b"seq", b"now", b"flags", b"x", b"y", b"h", b"ox", b"oy", b"oh",
    b"vl", b"vr", b"i2cf", b"cyc", b"posl", b"posr", b"dutl", b"dutr",
    b"lexc", b"wrng", b"cycovr",
]


def test_widest_realistic_full_frame_fits_comfortably_under_radio_cap(wg):
    """Realistic-but-large values (long-running-session magnitudes, not
    pathological INT32_MIN) for every one of the 20 POSE+FULL columns
    -- `flags` is the one hex column."""
    values = [
        127, 123456789, -1, -123456, -123456, -18000, -123456, -123456,
        -18000, -1000, -1000, 999999, 12345678, -1234567, -1234567,
        -1000, -1000, 9999, 9999, 9999,
    ]
    hexness = [False, False, True] + [False] * 17
    columns = list(zip(_FULL_COLUMN_NAMES, values, hexness))
    assert len(columns) == 20

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    thdr_line, t_line = writes  # no reliability line (2026-08-26, S8.5)

    # Measured, not guessed -- see this test's own docstring and this
    # ticket's final report for the exact numbers (86 B / 144 B as of
    # sprint 010 ticket 002; unchanged by that ticket's 200->240 raise,
    # since these numbers were never close to either cap). The 200/160
    # thresholds below are pinned safety margins, not a restatement of
    # the cap itself -- RadioTransport::kMaxPayloadBytes is 240 as of
    # this ticket (see test_wire_constants_drift.py's four-way equality
    # test), so both lines actually clear the real cap by 56-96 bytes,
    # comfortably more headroom than these thresholds alone show.
    assert len(thdr_line) < 200
    assert len(t_line) < 200
    assert len(t_line) <= 160  # comfortable margin under the 240-byte cap


def test_widest_pathological_int32_min_frame_confirms_open_question_2(wg):
    """The sprint.md architecture doc's own Open Question 2 flags an
    UNVERIFIED worry: an all-columns-near-INT32_MIN FULL frame could
    approach ~240 bytes, close to RadioTransport's truncation cap. This
    test turns that worry into a pinned, measured fact rather than
    leaving it a guess. It is not this ticket's job to trim FULL's
    column set in response (Open Question 2's own resolution: that
    choice is deferred to whichever ticket's test actually fails on
    real projected values, i.e. ticket 004, not this purely-formatting
    one).

    Sprint 010 ticket 002 raised RadioTransport::kMaxPayloadBytes from
    200 to 240 (radio-rx-capacity-fragmentation.md). Under the OLD cap
    this 239-byte pathological frame was 39 bytes OVER and would have
    been silently truncated on the radio transport; under the NEW
    240-byte cap it now FITS, with exactly 1 byte of headroom -- thin,
    not comfortable (flagged in sprint.md's Open Questions). The
    239-byte pinned measurement itself is preserved unchanged (it
    remains the project's only pinned evidence of the FULL column set's
    true worst case); only the boundary assertions below move to match
    the new cap."""
    values = [-2147483648] * 20
    values[2] = -1  # the one hex column ("flags") -- 0xffffffff, 8 chars
    hexness = [False, False, True] + [False] * 17
    columns = list(zip(_FULL_COLUMN_NAMES, values, hexness))

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    _thdr_line, t_line = writes  # no reliability line (2026-08-26, S8.5)

    # Pinned measurement: 239 bytes, unchanged since this test was
    # first written (sprint 004 ticket 003) -- this ticket does not
    # change the FORMATTING, only the cap it is measured against. The
    # pathological case now fits within RadioTransport's 240-byte cap
    # (radio_transport.h's kMaxPayloadBytes, sprint 010 ticket 002),
    # with exactly 1 byte of headroom, and stays within the wire's own
    # 240-byte line ceiling either way (WireHandler formats into a
    # 240-byte member buffer -- see emitBuf_'s own comment in
    # wire_handler.h).
    assert len(t_line) == 239
    assert len(t_line) <= 240  # fits the new cap, 1 B of headroom -- thin
