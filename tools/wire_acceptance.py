#!/usr/bin/env python3
"""End-to-end acceptance test against REAL firmware on a REAL robot.

Good cases, bad cases, and whether the robot actually MOVES.

    uv run python tools/wire_acceptance.py --usb /dev/cu.usbmodemXXXX
    uv run python tools/wire_acceptance.py --gauti            # ssh ros@gauti
    uv run python tools/wire_acceptance.py --radio 4          # relay pool

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
import re
import subprocess
import sys
import time

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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--usb', metavar='PORT', help='local serial port')
    g.add_argument('--gauti', action='store_true',
                   help="vevov's port, over ssh ros@gauti")
    g.add_argument('--radio', metavar='CH', type=int,
                   help='torture relay pool on this channel')
    ap.add_argument('--distance', type=int, default=200,
                    help='motion test distance per wheel in MM (default 200)')
    ap.add_argument('--no-motion', action='store_true',
                    help='skip the motion section (bench board, wheels up)')
    a = ap.parse_args()

    if a.usb:
        link, where = UsbLink(a.usb), f'USB {a.usb}'
    elif a.gauti:
        link, where = GautiLink(), 'gauti -> vevov USB'
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
        # ORDER MATTERS. run_bad_cases() sends ESTOP, which LATCHES
        # estopLatch_ (core/diffdrive.cpp) and makes checkCommandable()
        # refuse every later motion command at intake. There is no wire
        # verb that clears it -- _estopClear() exists only as a block
        # (src/blocks/stop.ts) -- so once ESTOP has been sent, motion
        # cannot be tested again until the board reboots. Motion
        # therefore runs FIRST, and ESTOP is left to the end.
        run_good_cases(link)
        if a.no_motion:
            print('\n=== MOTION: skipped (--no-motion) ===')
        else:
            run_motion(link, a.distance)
        run_bad_cases(link)
    finally:
        link.close()

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
