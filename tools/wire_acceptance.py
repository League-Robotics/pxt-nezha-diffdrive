#!/usr/bin/env python3
"""End-to-end acceptance test against REAL firmware on a REAL robot.

Good cases, bad cases, and whether the robot actually MOVES.

    uv run python tools/wire_acceptance.py --usb /dev/cu.usbmodemXXXX
    uv run python tools/wire_acceptance.py --gauti            # ssh ros@gauti
    uv run python tools/wire_acceptance.py --radio 4          # relay pool
    uv run python tools/wire_acceptance.py --tcp 192.168.1.147:PORT
                                                              # farm serial daemon
    uv run python tools/wire_acceptance.py --wifi tovez       # WiFi, by mDNS/broadcast
    uv run python tools/wire_acceptance.py --wifi 192.168.1.196
                                                              # WiFi, by address

`--all-verbs` (default on) additionally exercises EVERY verb in the v6
table -- HELLO PING ID VER STATUS HELP GET SET TLM WHEELS_X WHEELS_V
MOVE_X MOVE_V GO_TO_R GO_TO_W STOP ESTOP RUN -- plus the cleartext
`RUN:` carve-out, so a transport port (the WiFi link, 2026-09-02) is
judged against the whole protocol, not the handful of verbs the
original bad/good/motion sections happened to touch.

Why this exists: the unit suite under tests/host/ drives WireHandler
through a ctypes shim, so it proves the handler's logic and nothing
about the hex on a board. Every wire regression this project shipped in
one day -- a bare HELP silently dropped, a resent id acking with no
payload, GET's unknown name answering nothing, a motion verb with no id
vanishing without trace -- passed the unit suite. They were only visible
by typing at a real robot.

THREE OUTCOMES, not two:
  PASS     the behaviour is correct
  FAIL     the behaviour is wrong -- a defect
  BLOCKED  a precondition is unmet, so the case could not be judged
           (e.g. the Nezha brick has no power, so nothing can move).
           BLOCKED is NOT a pass. It is reported separately and sets a
           distinct exit code, because a suite that quietly counts
           un-run cases as green is worse than no suite.

MOTION IS PROVEN BY MOVEMENT, NOT BY A RECEIPT. Odometry cannot detect
its own failure to move -- it integrates encoder deltas and will report
the full commanded distance on a robot that never budged (CLAUDE.md).
So this asserts on an ENCODER DELTA, and, when the overhead camera is
reachable, cross-checks against the tag. An `ack` is not evidence.
"""
import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wifilink  # noqa: E402  (tools/wifilink.py -- the UDP link + discovery)

# --------------------------------------------------------------- results
PASS, FAIL, BLOCKED = 'PASS', 'FAIL', 'BLOCKED'
results = []


def record(outcome, name, detail=''):
    results.append((outcome, name, detail))
    print(f'  [{outcome:7s}] {name}')
    if detail and outcome != PASS:
        print(f'            {detail}')


# ------------------------------------------------------------- transports
class UsbLink:
    """Local serial port."""

    def __init__(self, port):
        import serial
        self.p = serial.Serial(port, 115200, timeout=0.1)
        self.buf = b''
        time.sleep(0.8)
        self.read(0.4)

    def read(self, sec):
        end = time.time() + sec
        got = []
        while time.time() < end:
            c = self.p.read(4096)
            if c:
                self.buf += c
                while b'\n' in self.buf:
                    r, self.buf = self.buf.split(b'\n', 1)
                    t = r.decode('ascii', 'replace').strip()
                    if t:
                        got.append(t)
        return got

    def ask(self, line, sec=0.8):
        self.p.write(line.encode() + b'\n')
        self.p.flush()
        return self.read(sec)

    def close(self):
        self.p.close()


class GautiLink:
    """vevov's serial port, reached over ssh. One python process on the
    Pi per call would be far too slow, so a single helper is uploaded
    and driven line-by-line over stdin."""

    HELPER = r'''
import sys, time, serial
p = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
time.sleep(0.8)
buf = b''
def read(sec):
    global buf
    end = time.time() + sec
    got = []
    while time.time() < end:
        c = p.read(4096)
        if c:
            buf += c
            while b'\n' in buf:
                r, buf = buf.split(b'\n', 1)
                t = r.decode('ascii', 'replace').strip()
                if t: got.append(t)
    return got
read(0.4)
for raw in sys.stdin:
    raw = raw.rstrip('\n')
    if not raw: continue
    cmd, _, secs = raw.partition('\x01')
    p.write(cmd.encode() + b'\n'); p.flush()
    for t in read(float(secs or 0.8)):
        print('R ' + t, flush=True)
    print('END', flush=True)
'''

    def __init__(self):
        subprocess.run(['ssh', 'ros@gauti', 'cat > /tmp/_acc_helper.py'],
                       input=self.HELPER.encode(), check=True)
        self.proc = subprocess.Popen(
            ['ssh', 'ros@gauti', 'python3', '-u', '/tmp/_acc_helper.py'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def ask(self, line, sec=0.8):
        self.proc.stdin.write(f'{line}\x01{sec}\n')
        self.proc.stdin.flush()
        out = []
        for ln in self.proc.stdout:
            ln = ln.rstrip('\n')
            if ln == 'END':
                break
            if ln.startswith('R '):
                out.append(ln[2:])
        return out

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class RadioLink:
    """Through the torture relay pool. NOTE: measured 66-83% per-line
    delivery, so absence of a reply is NOT evidence of absence of the
    behaviour. Every negative assertion is retried; see `missing()`."""

    def __init__(self, channel, host='192.168.1.12', port=8760):
        import socket
        self.s = socket.create_connection((host, port), timeout=15)
        self.buf = b''
        time.sleep(1.0)
        self.read(1.5)
        for c in (f'!CG {channel} 10', '!GO'):
            self.s.sendall((c + '\n').encode())
            time.sleep(0.4)
            self.read(0.8)

    def read(self, sec):
        import socket as _s
        end = time.time() + sec
        got = []
        self.s.settimeout(0.25)
        while time.time() < end:
            try:
                c = self.s.recv(4096)
            except _s.timeout:
                continue
            if not c:
                break
            self.buf += c
            while b'\n' in self.buf:
                r, self.buf = self.buf.split(b'\n', 1)
                t = r.decode('ascii', 'replace').strip()
                if t.startswith('< '):
                    t = t[2:]
                if t:
                    got.append(t)
        return got

    def ask(self, line, sec=1.2):
        self.s.sendall(line.encode() + b'\n')
        return self.read(sec)

    def close(self):
        self.s.close()


class TcpLink:
    """A farm node's serial daemon (mbdeploy serve, `_mbserial._tcp`):
    a raw, lossless byte pipe to the board's USB serial port."""

    def __init__(self, hostport):
        import socket
        host, _, port = hostport.rpartition(':')
        self.s = socket.create_connection((host, int(port)), timeout=15)
        self.s.settimeout(0.1)
        self.buf = b''
        time.sleep(0.5)
        self.read(0.5)

    def read(self, sec):
        import socket as _s
        end = time.time() + sec
        got = []
        while time.time() < end:
            try:
                c = self.s.recv(4096)
            except _s.timeout:
                continue
            if not c:
                break
            self.buf += c
            while b'\n' in self.buf:
                r, self.buf = self.buf.split(b'\n', 1)
                t = r.decode('ascii', 'replace').strip()
                if t:
                    got.append(t)
        return got

    def ask(self, line, sec=0.8):
        self.s.sendall(line.encode() + b'\n')
        return self.read(sec)

    def close(self):
        self.s.close()


class WifiLink:
    """The robot's own WiFi transport (src/comms/wifi_link.h): v6 over
    UDP :7654, one datagram per line. `target` is an IP, or a robot name
    resolved by mDNS (`<name>.local`) and then broadcast HELLO."""

    def __init__(self, target):
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', target):
            host = target
        else:
            host = wifilink.discover(target)
        self.host = host
        self.link = wifilink.WifiLink(host)
        time.sleep(0.3)
        self.read(0.5)

    def read(self, sec):
        return self.link.read(sec)

    def ask(self, line, sec=0.8):
        return self.link.ask(line, sec)

    def close(self):
        self.link.close()


# ------------------------------------------------------------- utilities
def has(out, *prefixes):
    return any(t.startswith(prefixes) for t in out)


def status_of(link):
    for _ in range(4):        # lossy transports get retries
        out = link.ask('STATUS', 1.2)
        for t in out:
            if t.startswith('status '):
                return t
    return ''


def kv(status_line, key, default=None):
    for tok in status_line.split():
        if tok.startswith(key + '='):
            return tok[len(key) + 1:]
    return default


def reset(link):
    link.ask('HELLO', 1.2)


def confirm_absent(link, cmd, prefix, tries=4):
    """A negative assertion that survives a lossy link: the behaviour is
    absent only if it fails to appear across `tries` attempts."""
    for _ in range(tries):
        if has(link.ask(cmd), prefix):
            return False
    return True


# ------------------------------------------------------------- the cases
def run_bad_cases(link):
    print('\n=== BAD CASES: every wrong line must SAY something ===')
    reset(link)

    for cmd in ('WHEELS_X 100 100 2000', 'GET', 'SET a 1', 'TLM', 'STOP',
                'MOVE_X 10 10'):
        out = link.ask(cmd)
        record(PASS if has(out, 'nack ') else FAIL,
               f'`{cmd}` with no id -> nack', str(out))

    record(PASS if confirm_absent(link, 'NOTAVERB', 'nack') else FAIL,
           'unrecognized verb, no id -> stays silent (shared channel)')

    reset(link)
    out = link.ask('GET nosuch.field #1')
    record(PASS if has(out, 'ack 1 ') and has(out, 'err 1 ') else FAIL,
           'GET unknown name -> ack AND err 1', str(out))

    out = link.ask('SET nosuch_field 1.0 #2')
    record(PASS if has(out, 'ack 2 ') and has(out, 'err 1 ') else FAIL,
           'SET unknown name -> ack AND err 1 (symmetric)', str(out))

    out = link.ask('SET group.alpha notanumber #3')
    record(PASS if has(out, 'nack ') and has(out, 'err ') else FAIL,
           'SET unparseable value -> nack + err', str(out))

    reset(link)
    out = link.ask('STOP extra junk #1')
    record(PASS if has(out, 'nack 1 ') and has(out, 'err 2 ') else FAIL,
           'wrong arity -> nack + err 2', str(out))

    reset(link)
    out = link.ask('WHEELS_X 100 100 1000 #0')
    record(PASS if has(out, 'nack ') else FAIL,
           '`#0` (never a legal id) -> nack, not a bare ack', str(out))
    for verb, pre in (('ID', 'id '), ('HELP', 'help ')):
        ok = any(has(link.ask(verb), pre) for _ in range(4))
        record(PASS if ok else FAIL,
               f'`{verb}` still answers after a #0 line')

    reset(link)
    link.ask('STOP #9')                       # gap: expectedNext_ is 1
    out = link.ask('ID')
    record(PASS if has(out, 'id ') and has(out, 'nack 1 ') else FAIL,
           'gap open -> query answers AND reminds', str(out))
    out = [t for t in link.ask('ESTOP')
           if not t.startswith(('t ', 'thdr '))]
    record(PASS if out == ['estop'] else FAIL,
           'ESTOP during a gap -> bare `estop`, no reminder', str(out))
    reset(link)
    out = link.ask('ID')
    record(PASS if has(out, 'id ') and not has(out, 'nack') else FAIL,
           'reminder clears after HELLO (no latch)', str(out))


def run_good_cases(link):
    print('\n=== GOOD CASES ===')
    reset(link)
    for verb, pre in (('PING', 'pong'), ('HELP', 'help '), ('ID', 'id '),
                      ('VER', 'ver '), ('STATUS', 'status ')):
        ok = any(has(link.ask(verb), pre) for _ in range(3))
        record(PASS if ok else FAIL, f'bare `{verb}` answers with no id')

    st = status_of(link)
    record(PASS if 'done=' in st and 'reason=' in st else FAIL,
           'STATUS carries done= and reason=', st)

    reset(link)
    out = link.ask('STOP #1')
    record(PASS if has(out, 'ack 1 ') else FAIL, 'STOP #1 -> ack 1', str(out))
    out = link.ask('STOP #2')
    record(PASS if has(out, 'ack 2 ') else FAIL,
           'sequence advances -> ack 2', str(out))
    out = link.ask('STOP #2')
    record(PASS if has(out, 'ack ') else FAIL,
           'resent #2 -> re-ack, not re-executed', str(out))


def next_id(lines, cur):
    """Track the host's sequence counter from what the robot ACTUALLY
    says, never by blind increment.

    Two hard-won rules, both of which cost a debugging session:
      * `nack N` means "resend N" -- a decode failure HOLDS the stream
        (S8.9). Incrementing after a nack opens a gap on the same wound.
      * UNSEQUENCED verbs (HELLO/PING/ESTOP/HELP/ID/VER/STATUS) consume
        NO id. Bumping a counter for them desyncs the very next real
        command -- the same defect that was latent in robotlink's
        _V6_VERBS for ESTOP.
    """
    for t in lines:
        m = re.match(r'^nack (\d+)', t)
        if m:
            return int(m.group(1))
        m = re.match(r'^ack (\d+)', t)
        if m:
            return int(m.group(1)) + 1
    return cur


def run_motion(link, distance_mm):
    """Do the WHEELS TURN?

    On a bench stand this is the whole question and needs no camera:
    telemetry's vl/vr (wheel velocity) going non-zero, and x (odometry)
    advancing, while a move is commanded.

    Deliberately does NOT call RUN:probe first. That touches the OTOS
    over I2C and hangs indefinitely on a board whose OTOS does not
    answer -- measured on tovez running PRE-2026-08-27 firmware, so it
    is not a regression from the wire work, but it will kill the program
    and take the rest of the run with it. Wheels do not need it.
    """
    print('\n=== MOTION: do the wheels turn? ===')
    reset(link)
    seq = 1

    out = link.ask(f'TLM POSE #{seq}', 2.0)
    seq = next_id(out, seq)
    cols = None
    for t in out:
        if t.startswith('thdr '):
            cols = t.split()[1:]
    record(PASS if cols else FAIL, 'telemetry stream started (thdr seen)',
           str(out[:3]))
    if not cols:
        record(BLOCKED, 'motion: wheels turned', 'no telemetry to judge by')
        return

    def frames(lines):
        out = []
        for t in lines:
            if t.startswith('t '):
                parts = t.split()[1:]
                if len(parts) == len(cols):
                    out.append(dict(zip(cols, parts)))
        return out

    # PING is unsequenced, so it consumes no id -- a safe way to hold
    # the port open and collect telemetry frames between commands.
    base = frames(link.ask('PING', 1.0))
    x0 = int(base[-1]['x']) if base else 0

    # ARITY IS EXACT, and getting it wrong is a decode failure, not a
    # move: WHEELS_X <left mm> <right mm> <cruise> <timeout ms>. The
    # three-field form reported from the field (`WHEELS_X 100 100 2000`)
    # is wrong arity and answers `nack` + `err 2`.
    cmd = f'WHEELS_X {distance_mm} {distance_mm} 120 5000 #{seq}'
    out = link.ask(cmd, 0.5)
    record(PASS if has(out, f'ack {seq} ') else FAIL,
           f'{cmd} accepted', str([t for t in out if not t.startswith('t ')][:3]))

    moving = frames(link.ask('PING', 3.5))
    vl = [abs(int(f['vl'])) for f in moving if 'vl' in f]
    vr = [abs(int(f['vr'])) for f in moving if 'vr' in f]
    x1 = int(moving[-1]['x']) if moving else x0
    turned = (max(vl) if vl else 0) > 0 or (max(vr) if vr else 0) > 0 \
        or abs(x1 - x0) > 5
    record(PASS if turned else FAIL,
           'WHEELS TURNED (vl/vr non-zero or odometry advanced)',
           f'vl max={max(vl) if vl else 0} vr max={max(vr) if vr else 0} '
           f'x {x0} -> {x1}')

    seq = next_id(out, seq)
    out = link.ask(f'STOP #{seq}', 1.0)
    seq = next_id(out, seq)
    link.ask(f'TLM OFF #{seq}', 1.5)   # quiet the wire for later sections


ALL_VERBS = ('HELLO', 'PING', 'ID', 'VER', 'STATUS', 'HELP', 'GET', 'SET',
             'TLM', 'WHEELS_X', 'WHEELS_V', 'MOVE_X', 'MOVE_V', 'GO_TO_R',
             'GO_TO_W', 'STOP', 'ESTOP', 'RUN')


def _frames(lines, cols):
    out = []
    for t in lines:
        if t.startswith('t ') and cols:
            parts = t.split()[1:]
            if len(parts) == len(cols):
                out.append(dict(zip(cols, parts)))
    return out


def _moved(frames):
    vl = [abs(int(f['vl'])) for f in frames if 'vl' in f]
    vr = [abs(int(f['vr'])) for f in frames if 'vr' in f]
    return (max(vl) if vl else 0) > 0 or (max(vr) if vr else 0) > 0


def _quiet(lines):
    return [t for t in lines if not t.startswith(('t ', 'thdr '))]


def run_all_verbs(link, motion=True, estop=True):
    """Every verb in the v6 table, once each, in a sequence that keeps
    the robot's expectedNext_ tracked from its OWN acks (never a blind
    increment -- see next_id()). ESTOP is deliberately LAST: it latches
    (see main()'s ordering note)."""
    print('\n=== ALL VERBS: every entry in the v6 table, over this transport ===')
    reset(link)                                    # HELLO
    seq = 1

    # --- the seven unsequenced verbs -----------------------------------
    out = link.ask('HELLO', 1.2)
    record(PASS if has(out, 'device ') else FAIL, 'HELLO -> device banner', str(out))
    for verb, pre in (('PING', 'pong '), ('ID', 'id '), ('VER', 'ver '),
                      ('STATUS', 'status ')):
        out = None
        for _ in range(3):
            out = link.ask(verb)
            if has(out, pre):
                break
        record(PASS if has(out, pre) else FAIL, f'{verb} -> {pre.strip()}', str(out))
    idline = next((t for t in link.ask('ID') if t.startswith('id ')), '')
    parts = idline.split()
    record(PASS if len(parts) == 5 else FAIL,
           'ID carries drivetrain profile version NAME (4 fields)', idline)
    help_lines = []
    for _ in range(3):
        help_lines = [t for t in link.ask('HELP', 1.5) if t.startswith('help')]
        if help_lines:
            break
    listed = ' '.join(help_lines)
    missing = [v for v in ALL_VERBS if v not in listed.split()]
    record(PASS if help_lines and not missing else FAIL,
           'HELP lists all 18 verbs', f'missing={missing} got={help_lines}')

    # --- GET / SET (sequenced, order-dependent) --------------------------
    out = link.ask(f'GET #{seq}', 2.0)
    gets = [t for t in out if t.startswith('get ')]
    record(PASS if has(out, f'ack {seq} ') and gets else FAIL,
           'bare GET -> ack + one `get` line per field', f'{len(gets)} fields, {out[:2]}')
    seq = next_id(out, seq)
    out = link.ask(f'GET max_duty #{seq}')
    val = next((t.split()[2] for t in out if t.startswith('get max_duty ')), None)
    record(PASS if has(out, f'ack {seq} ') and val is not None else FAIL,
           'GET max_duty -> get max_duty <v>', str(out))
    seq = next_id(out, seq)
    if val is not None:
        out = link.ask(f'SET max_duty {val} #{seq}')
        record(PASS if has(out, f'ack {seq} ') and not has(out, 'err ') else FAIL,
               'SET max_duty <same> -> ack, no err', str(out))
        seq = next_id(out, seq)
        out = link.ask(f'GET max_duty #{seq}')
        val2 = next((t.split()[2] for t in out if t.startswith('get max_duty ')), None)
        record(PASS if val2 == val else FAIL, 'GET reads back the SET value',
               f'{val} -> {val2}')
        seq = next_id(out, seq)

    # --- TLM modes -------------------------------------------------------
    cols = None
    out = link.ask(f'TLM POSE #{seq}', 1.5)
    for t in out:
        if t.startswith('thdr '):
            cols = t.split()[1:]
    frames = _frames(out, cols)
    record(PASS if has(out, f'ack {seq} ') and cols and frames else FAIL,
           'TLM POSE -> ack, thdr, t frames', f'cols={cols} frames={len(frames)}')
    seq = next_id(out, seq)
    pose_cols = cols
    out = link.ask(f'TLM FULL #{seq}', 1.5)
    full_cols = None
    for t in out:
        if t.startswith('thdr '):
            full_cols = t.split()[1:]
    record(PASS if has(out, f'ack {seq} ') and full_cols and
           (not pose_cols or len(full_cols) >= len(pose_cols)) else FAIL,
           'TLM FULL -> ack + a (wider) thdr', f'cols={full_cols}')
    seq = next_id(out, seq)
    cols = full_cols or pose_cols
    for mode in ('AUTO', 'BUFFER'):
        out = link.ask(f'TLM {mode} #{seq}', 1.0)
        record(PASS if has(out, f'ack {seq} ') and not has(out, 'nack') else FAIL,
               f'TLM {mode} -> ack', str(_quiet(out)))
        seq = next_id(out, seq)
    # TLM NOW is "a one-shot request in the CURRENT subscription's shape"
    # (wire_adapter.cpp): it never changes the mode, so with a live POSE
    # subscription it acks and frames keep coming; with the mode OFF it
    # acks and nothing is emitted. Both halves are checked.
    out = link.ask(f'TLM NOW #{seq}', 1.0)
    record(PASS if has(out, f'ack {seq} ') and not has(out, 'nack') else FAIL,
           'TLM NOW (while subscribed) -> ack, mode unchanged', str(_quiet(out)))
    seq = next_id(out, seq)
    out = link.ask(f'TLM OFF #{seq}', 1.0)
    seq = next_id(out, seq)
    after = link.read(0.8)
    record(PASS if has(out, 'ack ') and not [t for t in after if t.startswith('t ')] else FAIL,
           'TLM OFF -> ack, frames stop', f'{len(after)} lines after')
    out = link.ask(f'TLM NOW #{seq}', 1.0)
    record(PASS if has(out, f'ack {seq} ') and not has(out, 'nack') else FAIL,
           'TLM NOW (while off) -> ack', str(_quiet(out)))
    seq = next_id(out, seq)
    after = link.read(0.6)
    record(PASS if not [t for t in after if t.startswith('t ')] else FAIL,
           'TLM NOW never starts a stream', f'{len(after)} lines after')

    # --- the six motion verbs + STOP -------------------------------------
    def motion_case(cmd, label, accept_err=()):
        nonlocal seq, cols
        out = link.ask(f'TLM POSE #{seq}', 0.8)
        seq = next_id(out, seq)
        # The POSE column set differs from FULL's -- take the header
        # this subscription actually announced, or frames never match.
        for t in out:
            if t.startswith('thdr '):
                cols = t.split()[1:]
        line = f'{cmd} #{seq}'
        out = link.ask(line, 0.5)
        err = next((t for t in out if t.startswith('err ')), None)
        acked = has(out, f'ack {seq} ')
        seq = next_id(out, seq)
        if not acked:
            record(FAIL, f'{label}: accepted', str(_quiet(out)))
        elif err and err.split()[1] in accept_err:
            record(PASS, f'{label}: ack + refused on merit ({err}) -- acceptable here',
                   str(_quiet(out)))
        elif err:
            record(FAIL, f'{label}: accepted but refused', str(_quiet(out)))
        else:
            record(PASS, f'{label}: ack, no err')
            if motion:
                moving = _frames(link.ask('PING', 2.5), cols)
                record(PASS if _moved(moving) else FAIL,
                       f'{label}: WHEELS TURNED (vl/vr non-zero)',
                       f'{len(moving)} frames')
        out = link.ask(f'STOP #{seq}', 0.8)
        record(PASS if has(out, f'ack {seq} ') else FAIL, f'STOP after {label} -> ack',
               str(_quiet(out)))
        seq = next_id(out, seq)
        out = link.ask(f'TLM OFF #{seq}', 0.8)
        seq = next_id(out, seq)
        link.read(0.3)

    motion_case('WHEELS_V 100 100 1500', 'WHEELS_V')
    motion_case('WHEELS_X 150 150 120 4000', 'WHEELS_X')
    motion_case('MOVE_X 150 0 120 4000', 'MOVE_X')
    motion_case('MOVE_V 100 0 1500', 'MOVE_V')
    motion_case('GO_TO_R 150 0 120 10 4000', 'GO_TO_R')
    # GO_TO_W needs a world pose source; ERR_NOT_CONFIGURED (8) or
    # ERR_UNIMPLEMENTED (6) without one is a correct refusal, not a wire
    # defect.
    motion_case('GO_TO_W 0 0 120 10 3000', 'GO_TO_W', accept_err=('6', '8'))

    out = link.ask(f'STOP now #{seq}', 0.8)
    record(PASS if has(out, f'ack {seq} ') and not has(out, 'err ') else FAIL,
           'STOP now -> ack', str(_quiet(out)))
    seq = next_id(out, seq)

    # --- RUN, both forms ---------------------------------------------------
    out = link.ask(f'RUN nosuchfunction #{seq}', 1.0)
    record(PASS if has(out, f'ack {seq} ') and has(out, 'err 1 ') else FAIL,
           'v6 RUN <unknown> -> ack + err 1 (empty allowlist)', str(_quiet(out)))
    seq = next_id(out, seq)
    out = None
    for _ in range(3):
        out = link.ask('RUN:gap', 1.5)
        if has(out, 'GAP:'):
            break
    record(PASS if has(out, 'GAP:') else FAIL,
           'cleartext RUN:gap carve-out -> GAP: line', str(_quiet(out)))

    # --- ESTOP, last ---------------------------------------------------------
    if estop:
        out = _quiet(link.ask('ESTOP', 1.0))
        record(PASS if 'estop' in out else FAIL, 'ESTOP -> estop', str(out))
    else:
        print('  (ESTOP skipped: --no-estop, so a second transport can run '
              'motion on this boot)')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--usb', metavar='PORT', help='local serial port')
    g.add_argument('--gauti', action='store_true',
                   help="vevov's port, over ssh ros@gauti")
    g.add_argument('--radio', metavar='CH', type=int,
                   help='torture relay pool on this channel')
    g.add_argument('--tcp', metavar='HOST:PORT',
                   help="a farm node's serial daemon (mbdeploy serve)")
    g.add_argument('--wifi', metavar='NAME|IP',
                   help="the robot's own WiFi transport (UDP :7654); a name "
                        "is resolved by mDNS then broadcast")
    ap.add_argument('--distance', type=int, default=200,
                    help='motion test distance per wheel in MM (default 200)')
    ap.add_argument('--no-motion', action='store_true',
                    help='skip the motion section (bench board, wheels up)')
    ap.add_argument('--no-all-verbs', action='store_true',
                    help='skip the every-verb section')
    ap.add_argument('--only-all-verbs', action='store_true',
                    help='run ONLY the every-verb section (fresh-boot '
                         'friendly: no prior ESTOP latch)')
    ap.add_argument('--no-estop', action='store_true',
                    help="leave ESTOP out of the every-verb section, so the "
                         "latch it sets does not refuse a later transport's "
                         "motion cases on the same boot")
    a = ap.parse_args()

    if a.usb:
        link, where = UsbLink(a.usb), f'USB {a.usb}'
    elif a.gauti:
        link, where = GautiLink(), 'gauti -> vevov USB'
    elif a.tcp:
        link, where = TcpLink(a.tcp), f'serial daemon {a.tcp}'
    elif a.wifi:
        link = WifiLink(a.wifi)
        where = f'WiFi UDP {link.host}:{wifilink.ROBOT_PORT}'
    else:
        link, where = RadioLink(a.radio), f'radio ch{a.radio}'

    ident = ''
    for _ in range(4):
        for t in link.ask('HELLO', 1.5):
            if t.startswith('device '):
                ident = t
        if ident:
            break
    print(f'transport : {where}')
    print(f'identity  : {ident or "(no HELLO banner -- robot not answering)"}')
    if not ident:
        print('\nABORT: nothing answered HELLO. Nothing below would mean '
              'anything.')
        link.close()
        return 3

    try:
        # PRECONDITION: is the ADAPTER side alive, or only the wire stack?
        #
        # PING/ID/VER/HELP answer from the wire stack and cached
        # identity; STATUS is the first verb that reads kernel and brick
        # state through the adapter. A board where PING answers and
        # STATUS does not has a HEALTHY wire stack and a WEDGED adapter
        # -- measured on gopiv 2026-08-27 -- and running the rest of the
        # suite against it produces a page of FAILs that all say the same
        # thing and none of which are wire defects.
        #
        # This is also a strictly better probe than RUN:probe, which was
        # the old way to find this: RUN:probe touches the OTOS over I2C
        # and can itself kill the program, so it destroys the evidence it
        # is gathering. STATUS is read-only and cannot.
        alive = any(t.startswith('pong') for t in link.ask('PING', 1.5))
        if alive and not status_of(link):
            record(BLOCKED, 'adapter/brick side is wedged',
                   'PING answers but STATUS does not -- the wire stack is '
                   'healthy and the kernel/brick side is not. Check brick '
                   'power (a flat battery does this), then reflash. Running '
                   'the rest of the suite here would report wire defects '
                   'that are not there.')
            return 2

        # ORDER MATTERS. run_bad_cases() sends ESTOP, which LATCHES
        # estopLatch_ (core/diffdrive.cpp) and makes checkCommandable()
        # refuse every later motion command at intake. There is no wire
        # verb that clears it -- _estopClear() exists only as a block
        # (src/blocks/stop.ts) -- so once ESTOP has been sent, motion
        # cannot be tested again until the board reboots. Motion
        # therefore runs FIRST, and ESTOP is left to the end.
        if a.only_all_verbs:
            run_all_verbs(link, motion=not a.no_motion, estop=not a.no_estop)
            return _summary()
        run_good_cases(link)
        if a.no_motion:
            print('\n=== MOTION: skipped (--no-motion) ===')
        else:
            run_motion(link, a.distance)
        run_bad_cases(link)
        # run_bad_cases() ends with an ESTOP, which LATCHES -- so the
        # every-verb section's own motion cases would all be refused
        # after it. It runs its own reset first; on a board that has just
        # been ESTOPped the motion cases report the latch (err 8/10) as
        # FAIL, which is the honest answer. Prefer --no-all-verbs +
        # a fresh boot if only the classic sections are wanted.
        if not a.no_all_verbs:
            run_all_verbs(link, motion=not a.no_motion, estop=not a.no_estop)
    finally:
        link.close()
    return _summary()


def _summary():
    n_pass = sum(1 for o, _, _ in results if o == PASS)
    n_fail = sum(1 for o, _, _ in results if o == FAIL)
    n_block = sum(1 for o, _, _ in results if o == BLOCKED)
    print('\n' + '=' * 66)
    for outcome, name, _ in results:
        print(f'  {outcome:7s}  {name}')
    print('=' * 66)
    print(f'{n_pass} passed, {n_fail} failed, {n_block} blocked')
    if n_fail:
        print('\nFAILURES:')
        for outcome, name, detail in results:
            if outcome == FAIL:
                print(f'  - {name}\n      {detail}')
    if n_block:
        print('\nBLOCKED (not passes -- preconditions unmet):')
        for outcome, name, detail in results:
            if outcome == BLOCKED:
                print(f'  - {name}\n      {detail}')
    return 1 if n_fail else (2 if n_block else 0)


if __name__ == '__main__':
    sys.exit(main())
