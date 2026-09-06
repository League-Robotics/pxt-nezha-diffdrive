"""tools/link.py -- the one sequenced-wire protocol, shared by every carrier.

Four modules used to implement this independently (`robotlink.Link`,
`fieldlink._SequencedLink`, `wire_acceptance`'s link family and
`tests/calibration/turn_calibration.Link`), which meant four places to
fix when the contract moved and four chances to fix only three of them.
Sprint 034 ticket 006 collapses them onto the two objects below.

**Scope: the protocol only.**

*Inside*: sequence-id allocation, resend-with-the-same-id, reading the
robot's own `ack`/`nack` back into the counter, newline reassembly out
of arbitrary byte chunks, the sequenced/unsequenced verb split, and the
relay's control-plane setup lines.

*Outside*: how a socket or a serial port is opened, tuned, timed out and
closed. Each carrier keeps its own small transport class for that -- a
lossy relay, a lossless TCP daemon pipe, a local serial port and a
background-reader thread genuinely differ, and pretending otherwise is
how the four copies started.

This module imports nothing but the standard library, deliberately:
`tests/host/` and `tests/calibration/` import it on machines with no
robot, no pyserial and no `src/` tree.

`tools/rogo/` does NOT use this module and must never import it -- see
`tools/rogo/DESIGN.md`. Its duplicate line handling is deliberate: rogo
is stdlib-only *and* `pipx install`-able standalone, so it cannot depend
on anything under `tools/`.
"""
import re

# The relay pool, named once. `torture` is the pool host
# (`microbit-radio-relay`'s server); 8760 is its documented port. It was
# spelled three ways before this module existed, one of them as a bare
# IP that goes stale the day the host is renumbered.
RELAY_HOST = 'torture'
RELAY_PORT = 8760

# The relay prefixes frames it received over the air with '< ' on its
# control plane. Stripping it is what makes a relayed line and a direct
# serial line read identically to a caller.
_RELAY_RX_PREFIX = '< '

_ACK_RE = re.compile(r'^(ack|nack)\s+(\d+)')


def relay_setup_lines(channel: int, group: int) -> tuple:
    """The relay control-plane setup EVERY relay carrier sends, in order.

    `!GO` is deliberately not included: it switches the relay into the
    transparent data plane and each carrier follows it with its own,
    longer settle, so it stays at the call site where that timing lives.

    **All four lines, on every relay carrier** (sprint 034 ticket 006 --
    the ticket's "either every relay carrier sends it or none does").
    Two of the four carriers used to send a subset, on the reasoning
    that a relay boots at `mode RAW250 / power 7 / echo off` and the
    extra lines are no-ops. That reasoning does not hold, for two
    reasons taken from the relay's own README
    (`../microbit-radio-relay/README.md`, command summary):

    * **The relay PERSISTS its config.** `!DEFAULTS` exists precisely
      because saved settings survive a reset ("clear saved config
      (defaults next reset)"). "Defaults on a fresh board" describes a
      board nobody has configured -- not the shared, hand-driven relays
      these carriers actually get. A previous session's `!MODE
      MAKECODE` or `!P 3` is inherited in silence by any carrier that
      does not restate them, and the symptom is a robot that simply
      does not answer.
    * **`!ECHO` is a transponder, not terminal echo.** It bounces
      RECEIVED RADIO MESSAGES back over the air. Left on, the relay
      re-transmits the robot's own replies onto the channel the robot
      is listening to. That is worth turning off explicitly rather than
      assuming.

    Restating a value that already holds costs one line and one settle;
    inheriting a wrong one costs a debugging session. So: all of them,
    everywhere.
    """
    return ('!ECHO OFF', '!MODE RAW250', f'!CG {channel} {group}', '!P 7')


class LineBuffer:
    """Newline reassembly for a byte stream that arrives in arbitrary chunks.

    `feed()` takes whatever `recv()`/`read()` returned and gives back the
    COMPLETE lines in it, stripped, with the relay's `'< '` receive
    prefix removed and blank lines dropped; a trailing partial line is
    held until the rest of it arrives. That last part is the whole point:
    a socket read splits wherever the network felt like splitting, and
    every carrier that re-derived this was one `recv()` boundary away
    from silently losing an `ack`.

    The `'< '` strip is unconditional, including on a direct serial port
    where no relay is involved. Nothing the robot says begins with
    `'< '`, so there is no line to lose, and a conditional would just be
    a per-carrier flag that the carriers disagreed about -- which is the
    defect this module exists to remove.
    """

    def __init__(self) -> None:
        self._buf = b''

    def feed(self, chunk: bytes) -> list:
        """Complete lines in `chunk`, as a list of stripped `str`."""
        if not chunk:
            return []
        self._buf += chunk
        out = []
        while b'\n' in self._buf:
            raw, self._buf = self._buf.split(b'\n', 1)
            text = raw.decode('ascii', 'replace').strip()
            if text.startswith(_RELAY_RX_PREFIX):
                text = text[len(_RELAY_RX_PREFIX):]
            if text:
                out.append(text)
        return out

    def line(self, chunk: bytes):
        """The single line in `chunk`, or None -- for a caller that reads
        a line at a time (a pyserial `readline()`) rather than a block."""
        got = self.feed(chunk)
        return got[0] if got else None

    def reset(self) -> None:
        """Discard the held partial line (a port flush on the host side)."""
        self._buf = b''


class Sequencer:
    """The v6 sequence-id counter, and the one place ids are allocated.

    `seq` is the LAST id handed out, so the next allocation is `seq + 1`.
    The robot's `expectedNext_` starts at 1, so a fresh `Sequencer`
    starts at 0.

    `sequenced_verbs` is the firmware's set of sequenced verbs, supplied
    by the caller. It stays a literal in `tools/robotlink.py` because
    that is where `tests/host/test_wire_constants_drift.py` reads it
    from, as source text, to compare against `wire_handler.cpp`'s
    `kCommandTable` -- and because robotlink is the only caller that
    needs to CLASSIFY a line at all. The other three name the verb kind
    at the call site (`seqd()` vs `unseq()`) and construct this with no
    verb set, using `format(..., force=True)`.
    """

    def __init__(self, sequenced_verbs=None) -> None:
        self.seq = 0
        self.sequenced_verbs = frozenset(sequenced_verbs or ())

    def is_sequenced(self, line: str) -> bool:
        """True if `line`'s verb is one the firmware sequences.

        First token only. `RUN` (the v6 verb, `RUN <name>`) is
        sequenced; the cleartext `RUN:tour:wheels` is a single token
        with no space, goes through a different parser on the robot, and
        must stay bare (`.claude/rules/playfield-testing.md`).
        """
        return line.split(' ', 1)[0] in self.sequenced_verbs

    def format(self, line: str, force: bool = False) -> str:
        """Attach a sequence id; pass an unsequenced line through bare.

        Allocates AT MOST ONE id per logical command. A retransmit must
        reuse its ORIGINAL id, never take a fresh one, or it reads as a
        numeric gap rather than as the resend it is -- and the firmware
        stalls the stream on a gap deliberately, nacking everything
        after it until the "missing" id arrives. Callers therefore
        format ONCE and resend the identical string.

        `force=True` means "this is a sequenced verb, take my word for
        it" -- for the callers that know the verb kind at the call site
        and carry no verb table.

        A line that already carries a `#` is returned untouched, on
        either path: it has an id, whoever put it there.
        """
        if '#' in line:
            return line
        if not force and not self.is_sequenced(line):
            return line
        self.seq += 1
        return f'{line} #{self.seq}'

    def reset(self) -> int:
        """Counterpart to HELLO, which sets the robot to `expectedNext_`
        = 1 the instant it receives the line. Unconditional: the reset
        happens on the robot whether or not the host reads the banner
        back."""
        self.seq = 0
        return self.seq

    def observe_reply(self, line: str):
        """Set `seq` from a live `ack`/`nack` reply; None if `line` is neither.

        `ack N` means "N was accepted", so the next id to allocate is
        N + 1 and `seq` lands on N. `nack N` means something different --
        "send me N next" -- so the next id to allocate must BE N and
        `seq` lands on N - 1. Treating the two alike was sprint 024
        ticket 002's bug: it opened a fresh gap on the same wound the
        `nack` was reporting.
        """
        m = _ACK_RE.match(line)
        if not m:
            return None
        n = int(m.group(2))
        self.seq = n if m.group(1) == 'ack' else n - 1
        return self.seq
