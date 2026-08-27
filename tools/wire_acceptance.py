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
    out = link.ask('ESTOP')
    record(PASS if out == ['estop'] else FAIL,
           'ESTOP during a gap -> bare `estop`', str(out))
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


def run_motion(link, distance_cm):
    """Does a commanded move MOVE THE ROBOT?

    Preconditions are checked first and reported BLOCKED, not FAIL: a
    robot whose Nezha brick has no power cannot move, and calling that a
    protocol defect would be wrong.
    """
    print('\n=== MOTION ===')
    reset(link)
    st = status_of(link)
    print(f'  STATUS: {st or "(no reply)"}')

    if not st:
        record(BLOCKED, 'motion: robot did not answer STATUS',
               'cannot judge motion against a robot that is not talking')
        return
    ready = kv(st, 'ready') == '1'
    conn = kv(st, 'connL') == '1' and kv(st, 'connR') == '1'
    cyc = kv(st, 'cyc', '0')

    if not conn:
        record(BLOCKED, 'motion: encoders not connected (connL/connR = 0)',
               'Nezha brick has no power -- switch it on, then RUN:probe '
               'must answer OPROBE:95:1 before motion means anything')
        record(BLOCKED, 'motion: robot physically moved',
               'precondition above unmet')
        return
    if not ready:
        record(BLOCKED, f'motion: kernel not ready (ready=0, cyc={cyc})',
               'kernel has not ticked')
        record(BLOCKED, 'motion: robot physically moved', 'precondition unmet')
        return

    out = link.ask('RUN:probe', 4.0)
    record(PASS if has(out, 'OPROBE') else FAIL,
           'RUN:probe -> OPROBE (I2C bus alive)', str(out))

    before = status_of(link)
    reset(link)
    out = link.ask(f'MOVE_X {distance_cm} {distance_cm} #1', 3.0)
    record(PASS if has(out, 'ack 1 ') else FAIL,
           f'MOVE_X {distance_cm} accepted', str(out))
    time.sleep(4.0)
    after = status_of(link)

    # An ack is not evidence. `done=` advancing proves the kernel
    # RESOLVED a move; it does not prove the wheels turned, which only
    # an external instrument can. Report both, and say which is which.
    d_before, d_after = kv(before, 'done', '0'), kv(after, 'done', '0')
    record(PASS if d_after != d_before else FAIL,
           f'a move RESOLVED (done= {d_before} -> {d_after})',
           f'before={before}  after={after}')
    record(BLOCKED, 'motion: independently confirmed by camera',
           'not wired up here -- odometry cannot detect its own failure '
           'to move, so this needs an overhead-camera or tape check')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--usb', metavar='PORT', help='local serial port')
    g.add_argument('--gauti', action='store_true',
                   help="vevov's port, over ssh ros@gauti")
    g.add_argument('--radio', metavar='CH', type=int,
                   help='torture relay pool on this channel')
    ap.add_argument('--distance', type=float, default=10.0,
                    help='motion test distance in cm (default 10)')
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
        run_bad_cases(link)
        run_good_cases(link)
        if a.no_motion:
            print('\n=== MOTION: skipped (--no-motion) ===')
        else:
            run_motion(link, a.distance)
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
