"""tests/tools/test_link.py -- pins `tools/link.py`, the one sequenced-wire
protocol every carrier shares (sprint 034 ticket 006, code review
2026-09-02).

The contract used to be implemented four times -- `robotlink.Link`,
`fieldlink._SequencedLink`, `wire_acceptance`'s link family and
`tests/calibration/turn_calibration.Link` -- so a fix landed in one, two
or three of them. These tests pin the shared object directly, with an
injected fake socket and fake serial port: no robot, no relay, no
network. Nothing here is a MEASURED claim about hardware, because
nothing here touches any.

Run with::

    uv run pytest tests/tools/test_link.py
"""
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import link as linklib  # noqa: E402  (path must be set up first)


class FakeSocket:
    """A socket double for the carriers' `read()` loops: `recv()` hands
    back canned byte CHUNKS, which is the whole point -- a real socket
    splits wherever the network felt like splitting, not on line
    boundaries."""

    def __init__(self, chunks=()):
        self.sent = []
        self._chunks = list(chunks)

    def recv(self, _n):
        return self._chunks.pop(0) if self._chunks else b''

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, _t):
        pass

    def close(self):
        pass


# --------------------------------------------------------------- LineBuffer

def test_a_whole_line_in_one_chunk_comes_back_stripped():
    buf = linklib.LineBuffer()
    assert buf.feed(b'ack 1 0 none\n') == ['ack 1 0 none']


def test_partial_lines_reassemble_across_reads():
    # The defect this class exists to prevent: an `ack` split across two
    # recv() boundaries, dropped by a reader that decoded each chunk on
    # its own.
    buf = linklib.LineBuffer()
    sock = FakeSocket([b'ack ', b'1 0 no', b'ne\nstatus ready=1\n'])
    got = []
    for _ in range(3):
        got.extend(buf.feed(sock.recv(4096)))
    assert got == ['ack 1 0 none', 'status ready=1']


def test_a_trailing_partial_line_is_held_not_emitted():
    buf = linklib.LineBuffer()
    assert buf.feed(b'ack 1 0 none\npart') == ['ack 1 0 none']
    assert buf.feed(b'ial\n') == ['partial']


def test_several_lines_in_one_chunk_all_come_back_in_order():
    buf = linklib.LineBuffer()
    assert buf.feed(b'a\nb\nc\n') == ['a', 'b', 'c']


def test_the_relay_receive_prefix_is_stripped():
    # The relay prefixes frames it received over the air with '< ' on
    # its control plane; a caller must see the robot's own line.
    buf = linklib.LineBuffer()
    assert buf.feed(b'< nack 5 0 none\n') == ['nack 5 0 none']


def test_blank_lines_are_dropped():
    buf = linklib.LineBuffer()
    assert buf.feed(b'\n\nack 1\n \n') == ['ack 1']


def test_an_empty_read_yields_nothing_and_keeps_the_partial():
    buf = linklib.LineBuffer()
    buf.feed(b'ack ')
    assert buf.feed(b'') == []
    assert buf.feed(b'1\n') == ['ack 1']


def test_reset_discards_the_held_partial():
    buf = linklib.LineBuffer()
    buf.feed(b'half a li')
    buf.reset()
    assert buf.feed(b'ne\n') == ['ne']


def test_line_returns_one_line_or_none():
    buf = linklib.LineBuffer()
    assert buf.line(b'') is None
    assert buf.line(b'< pong 3\n') == 'pong 3'


def test_undecodable_bytes_do_not_raise():
    buf = linklib.LineBuffer()
    assert buf.feed(b'\xff\xfeack 1\n') != []


# ---------------------------------------------------------------- Sequencer

_VERBS = frozenset(('GET', 'SET', 'MOVE_X', 'RUN'))


def test_the_first_id_allocated_is_1():
    # The robot's expectedNext_ starts at 1, so a fresh Sequencer must
    # hand out #1 first -- an off-by-one here opens a numeric gap on the
    # very first command and stalls the stream on purpose.
    seq = linklib.Sequencer(_VERBS)
    assert seq.seq == 0
    assert seq.format('MOVE_X 200 0 150 5000') == 'MOVE_X 200 0 150 5000 #1'


def test_ids_advance_by_one_per_sequenced_command():
    seq = linklib.Sequencer(_VERBS)
    assert seq.format('GET lag') == 'GET lag #1'
    assert seq.format('SET lag 0.04') == 'SET lag 0.04 #2'
    assert seq.seq == 2


def test_a_resend_reuses_its_id_because_format_runs_once():
    """A retransmit must carry its ORIGINAL id. This is the contract the
    callers implement by formatting ONCE outside their retry loop; here
    it is pinned as the property that makes that possible -- the
    formatted string is a value the caller can resend verbatim."""
    seq = linklib.Sequencer(_VERBS)
    wire = seq.format('SET lag 0.04')
    sock = FakeSocket()
    for _ in range(3):
        sock.sendall((wire + '\n').encode())
    assert sock.sent == [b'SET lag 0.04 #1\n'] * 3
    assert seq.seq == 1, 'three resends must burn exactly one id'


def test_re_formatting_an_already_numbered_line_does_not_take_a_fresh_id():
    """The defect this guards: a retry loop that re-formats each attempt
    would allocate #1, #2, #3 for ONE logical command. The second and
    third present to the robot as numeric gaps and the stream stalls,
    nacking everything after them until the 'missing' id arrives."""
    seq = linklib.Sequencer(_VERBS)
    first = seq.format('SET lag 0.04')
    again = seq.format(first)
    assert again == first == 'SET lag 0.04 #1'
    assert seq.seq == 1


def test_an_unsequenced_verb_goes_out_bare():
    # The firmware's seven exemptions consume no id. Appending one would
    # burn an id the robot never acks, desyncing the next real command.
    seq = linklib.Sequencer(_VERBS)
    for verb in ('HELLO', 'PING', 'ESTOP', 'HELP', 'ID', 'VER', 'STATUS'):
        assert seq.format(verb) == verb
    assert seq.seq == 0


def test_an_unknown_verb_is_left_alone_and_consumes_nothing():
    seq = linklib.Sequencer(_VERBS)
    assert seq.format('NOTAVERB 1 2') == 'NOTAVERB 1 2'
    assert seq.seq == 0


def test_run_is_sequenced_including_its_arguments():
    # `RUN <name> [arg...]` is an ordinary sequenced v6 verb. It has been
    # since 2026-09-07, when the cleartext `RUN:<name>` carve-out -- a
    # single token that used to reach a DIFFERENT parser on the robot and
    # so had to stay bare -- was deleted. There is no unsequenced RUN
    # spelling left; `RUN:tour:wheels` is now just an unknown verb.
    seq = linklib.Sequencer(_VERBS)
    assert seq.format('RUN tour') == 'RUN tour #1'
    assert seq.format('RUN tour wheels') == 'RUN tour wheels #2'
    assert seq.seq == 2


def test_force_sequences_a_verb_the_sequencer_has_no_table_for():
    # fieldlink/turn_calibration name the verb kind at the call site
    # (seqd vs unseq) and construct a Sequencer with no verb table.
    seq = linklib.Sequencer()
    assert seq.format('SET lag 0.04', force=True) == 'SET lag 0.04 #1'


def test_force_still_refuses_to_renumber_a_line_that_has_an_id():
    seq = linklib.Sequencer()
    wire = seq.format('SET lag 0.04', force=True)
    assert seq.format(wire, force=True) == wire
    assert seq.seq == 1


def test_is_sequenced_reads_the_first_token_only():
    seq = linklib.Sequencer(_VERBS)
    assert seq.is_sequenced('GET lag')
    assert not seq.is_sequenced('PING')
    assert not seq.is_sequenced('lag GET')


# --- observe_reply(): the ack/nack asymmetry -------------------------------

def test_ack_n_sets_seq_to_n():
    # `ack N` means "N was accepted", so the NEXT id is N + 1 and the
    # counter (which holds the LAST id handed out) lands on N.
    seq = linklib.Sequencer(_VERBS)
    assert seq.observe_reply('ack 7 0 none') == 7
    assert seq.format('GET') == 'GET #8'


def test_nack_n_sets_seq_to_n_minus_1_so_the_next_id_is_n():
    # `nack N` means "send me N next" -- a decode failure HOLDS the
    # stream. Treating it like an ack allocates N+1 and opens a fresh
    # gap on the same wound (sprint 024 ticket 002's bug).
    seq = linklib.Sequencer(_VERBS)
    assert seq.observe_reply('nack 5 0 none') == 4
    assert seq.format('GET') == 'GET #5'


def test_a_line_that_is_neither_ack_nor_nack_leaves_the_counter_alone():
    seq = linklib.Sequencer(_VERBS)
    seq.seq = 3
    for line in ('err 12 rebase', 'status ready=1', 'pong 4', 'device NEZHA2',
                 'ackerman 9', 'ack notanumber'):
        assert seq.observe_reply(line) is None, line
    assert seq.seq == 3


def test_reset_zeroes_the_counter_so_the_next_id_is_1():
    # HELLO's contract: the robot goes to expectedNext_ = 1 the instant
    # it receives the line, so the host counterpart is 0.
    seq = linklib.Sequencer(_VERBS)
    seq.format('GET')
    seq.format('GET')
    assert seq.reset() == 0
    assert seq.format('GET') == 'GET #1'


# ------------------------------------------------------- relay_setup_lines

def test_relay_setup_carries_the_addressed_channel_and_group():
    assert linklib.relay_setup_lines(55, 114)[2] == '!CG 55 114'


def test_relay_setup_is_the_full_sequence_in_robotlinks_order():
    # Settled by ticket 006: EVERY relay carrier sends all four, because
    # the relay persists its config across resets, so `!MODE RAW250` and
    # `!P 7` are not the no-ops "a fresh board defaults to them" implies.
    assert linklib.relay_setup_lines(37, 43) == (
        '!ECHO OFF', '!MODE RAW250', '!CG 37 43', '!P 7')


def test_relay_setup_does_not_include_go():
    # `!GO` switches the relay into the transparent data plane and each
    # carrier follows it with its own, longer settle.
    assert '!GO' not in linklib.relay_setup_lines(37, 43)


def test_the_relay_pool_is_named_not_numbered():
    # A bare IP goes stale the day the host is renumbered; wire_acceptance
    # carried `192.168.1.12` while the other two carriers used the name.
    assert linklib.RELAY_HOST == 'torture'
    assert linklib.RELAY_PORT == 8760


# ------------------------------------- the module's dependency constraints

def test_link_imports_nothing_but_the_standard_library():
    """`tests/host/` and `tests/calibration/` import this on machines
    with no pyserial and no robot, and `tools/rogo/` must be able to
    stay a standalone stdlib-only copy of the same rules."""
    import ast
    tree = ast.parse((_TOOLS_DIR / 'link.py').read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
    assert imported <= set(sys.stdlib_module_names), sorted(imported)


# ---------------------------- the callers actually use it (SUC-004) --------

def test_the_four_callers_import_link():
    """SUC-004: 'a change to the sequencing contract is made in one
    file'. Read as source text so this holds without importing pyserial
    or opening a socket."""
    targets = {
        'tools/robotlink.py': 'import link as linklib',
        'tools/fieldlink.py': 'import link as linklib',
        'tools/wire_acceptance.py': 'import link as linklib',
        'tests/calibration/turn_calibration.py': 'import link as linklib',
    }
    for path, needle in targets.items():
        text = (_REPO_ROOT / path).read_text()
        assert needle in text, f'{path} no longer imports tools/link.py'


def _string_literals(path):
    """Every string the module BUILDS, docstrings excluded -- so a
    comment or a docstring may quote a defect the code no longer has."""
    import ast
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, 'body', None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            out.append(node.value)
    return out


def test_no_relay_group_literal_survives_in_wire_acceptance():
    """`!CG {channel} 10` hard-coded the group to 10 for a fleet whose
    groups are 43, 60, 108 and 114 -- the relay tuned somewhere the
    robot was not, and the robot went silent with nothing to say why
    (sprint.md Open Question 2). It now resolves both halves through
    `robotlink.radio_address(robot)`."""
    path = _REPO_ROOT / 'tools' / 'wire_acceptance.py'
    built = [s for s in _string_literals(path) if '!CG' in s]
    assert built == [], (
        f'wire_acceptance.py builds a `!CG` line of its own again ({built}) '
        f'-- the relay setup belongs to link.relay_setup_lines()')
    assert 'radio_address' in path.read_text()


def test_turn_calibration_defaults_no_radio_group():
    """The same hard-coded 10, in the other place it lived: a
    `.get('radio_group', 10)` fallback in the sprint-031 bench
    program."""
    text = (_REPO_ROOT / 'tests' / 'calibration'
            / 'turn_calibration.py').read_text()
    assert "'radio_group', 10" not in text
    assert 'radio_group' in text


def test_rogo_imports_nothing_from_tools():
    """rogo's duplicate is DELIBERATE (sprint.md Design Rationale 3):
    its premise is `pipx install` with nothing but Python, so an import
    of `tools/link.py` would break it outright. Pinned here beside the
    thing it is a duplicate of, where a future consolidation pass will
    trip over it."""
    text = (_TOOLS_DIR / 'rogo' / 'rogo.py').read_text()
    for forbidden in ('import link', 'from link', 'import robotlink',
                      'from robotlink', 'import wifilink', 'from wifilink'):
        assert forbidden not in text, forbidden


if __name__ == '__main__':          # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
