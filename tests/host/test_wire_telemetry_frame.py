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
`emit_reliability()`/`take_sink_writes()`), and `_ack`/`_nack` helpers,
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


def test_first_frame_emits_thdr_then_t_then_reliability(wg):
    columns = [(b"x", 10, False), (b"y", -5, False), (b"flags", 0x2A, True)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"thdr x y flags\n", b"t 10 -5 2a\n", _ack(0)]


def test_second_frame_with_unchanged_columns_emits_only_t_and_reliability(wg):
    columns = [(b"x", 10, False), (b"y", -5, False), (b"flags", 0x2A, True)]
    wg.emit_telemetry(columns)
    wg.take_sink_writes()  # frame 1's thdr/t/ack -- not under test here

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes == [b"t 10 -5 2a\n", _ack(0)]


# ---------------------------------------------------------------------------
# Byte-exact ordering: thdr -> t -> ack/nack, as THREE SEPARATE
# Sink::write() calls -- asserted on the RecordingSink's own per-call
# log (take_sink_writes()), not just the concatenated buffer, so this
# is verifiable independent of whether writes happen to get
# concatenated in a real transport.
# ---------------------------------------------------------------------------


def test_emit_telemetry_writes_exactly_three_separate_lines_when_thdr_due(wg):
    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert len(writes) == 3
    assert writes[0] == b"thdr a\n"
    assert writes[1] == b"t 1\n"
    assert writes[2] == _ack(0)


def test_emit_telemetry_writes_exactly_two_separate_lines_when_thdr_not_due(wg):
    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    wg.take_sink_writes()

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert len(writes) == 2
    assert writes[0] == b"t 1\n"
    assert writes[1] == _ack(0)


def test_emit_telemetry_reliability_step_reflects_a_stalled_gap(wg):
    """The reliability keepalive emitTelemetry() calls internally is the
    SAME state emitReliability() alone reports -- a gap opened via
    feed() shows up as a `nack`, not an `ack`, on telemetry's own third
    write, exactly as it would standalone."""
    wg.feed(b"SET group.alpha 1.0 #5\n")  # opens a gap: expectedNext_ stays 1
    wg.take_sink()  # the nack from feed() itself -- not under test here

    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert len(writes) == 3
    assert writes[0] == b"thdr a\n"
    assert writes[1] == b"t 1\n"
    assert writes[2] == _nack(1)


# ---------------------------------------------------------------------------
# emitReliability() alone -- no Snapshot involved at all -- emits no
# `t` and no `thdr`, only the ack/nack line, matching the pre-split
# emitTelemetry()'s own behavior exactly (this is what lets the
# keepalive survive `TLM OFF`).
# ---------------------------------------------------------------------------


def test_emit_reliability_alone_emits_only_the_keepalive_line(wg):
    wg.emit_reliability()
    writes = wg.take_sink_writes()
    assert writes == [_ack(0)]


def test_emit_reliability_alone_never_touches_the_header_memo(wg):
    """Calling emitReliability() between two emitTelemetry() calls must
    not itself count as a "frame" for the header memo, and must not
    perturb headerChanged()'s own state -- it takes no Snapshot at all,
    so it has nothing to compare."""
    columns = [(b"a", 1, False)]
    wg.emit_telemetry(columns)
    wg.take_sink_writes()

    wg.emit_reliability()
    wg.take_sink_writes()

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    assert writes[0] == b"t 1\n"  # still no thdr -- unchanged columns


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
# Byte-width vs RadioTransport's silent 200-byte truncation cap
# (sprint.md Open Question 2). This ticket is pure formatting with no
# real WireAdapter projection (that is ticket 004's separate scope, and
# ticket 004 owns the AUTHORITATIVE widest-real-FULL-set test against
# actual scaled robot values) -- these two tests instead measure this
# ticket's own formatting mechanism against a hand-built stand-in for
# the sprint's documented 20-column POSE+FULL set
# ("seq now flags x y h ox oy oh vl vr i2cf cyc posl posr dutl dutr
# lexc wrng cycovr"), so a concrete, test-pinned number exists before
# ticket 004 lands the real one.
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
    thdr_line, t_line, _reliability_line = writes

    # Measured, not guessed -- see this test's own docstring and this
    # ticket's final report for the exact numbers.
    assert len(thdr_line) < 200
    assert len(t_line) < 200
    assert len(t_line) <= 160  # comfortable margin under the 200-byte cap


def test_widest_pathological_int32_min_frame_confirms_open_question_2(wg):
    """The sprint.md architecture doc's own Open Question 2 flags an
    UNVERIFIED worry: an all-columns-near-INT32_MIN FULL frame could
    approach ~240 bytes, over RadioTransport's 200-byte truncation cap.
    This test turns that worry into a pinned, measured fact rather than
    leaving it a guess -- it does NOT assert the pathological case
    fits (it does not), and it is not this ticket's job to trim FULL's
    column set in response (Open Question 2's own resolution: that
    choice is deferred to whichever ticket's test actually fails on
    real projected values, i.e. ticket 004, not this purely-formatting
    one)."""
    values = [-2147483648] * 20
    values[2] = -1  # the one hex column ("flags") -- 0xffffffff, 8 chars
    hexness = [False, False, True] + [False] * 17
    columns = list(zip(_FULL_COLUMN_NAMES, values, hexness))

    wg.emit_telemetry(columns)
    writes = wg.take_sink_writes()
    _thdr_line, t_line, _reliability_line = writes

    # Pinned measurement: the pathological case DOES exceed the
    # 200-byte radio cap, and stays within the wire's own 240-byte
    # line ceiling (WireHandler formats into a 240-byte member buffer
    # -- see emitBuf_'s own comment in wire_handler.h).
    assert len(t_line) > 200
    assert len(t_line) < 240
