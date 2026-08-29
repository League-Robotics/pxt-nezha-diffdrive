"""Capture per-wheel velocity on tovez over the mbrelay pool.

Bench run, wheels off the ground -- the only thing being measured is the
wheel-velocity kernel's tracking of a commanded WHEELS_V setpoint, which
is exactly what a wheels-up stand CAN measure honestly.

Radio contention is the hazard: streaming telemetry starves the inbound
command plane (MEASURED this session -- a WHEELS_V sent under a live TLM
stream did not execute inside a 2.5 s window, while the same verb on a
quiet link acked immediately). Every sequenced verb here is therefore
ack-verified and retransmitted with its ORIGINAL id, per protocol.md's
retransmit rule (a fresh id presents as a numeric gap and stalls on
purpose).
"""
import json
import re
import socket
import sys
import threading
import time

HOST, PORT = '192.168.1.12', 8760
CHANNEL, GROUP, POWER = 3, 10, 7

TRACKWIDTH_MM = 115.0          # radio-robot-lib/config/robots/tovez.json

POSE_COLS = 'seq now flags x y h ox oy oh vl vr i2cf'.split()
FULL_COLS = POSE_COLS + 'cyc posl posr dutl dutr lexc wrng cycovr'.split()


class Session:
    def __init__(self):
        self.s = socket.create_connection((HOST, PORT), timeout=10)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.s.settimeout(0.2)
        self.lines = []          # (host_ts, text)
        self.lock = threading.Lock()
        self.running = True
        self.t0 = time.time()
        self.rx = threading.Thread(target=self._reader, daemon=True)
        self.rx.start()
        time.sleep(0.5)
        self.relay = self._banner()
        self.send_raw(f'!P {POWER}')
        self.send_raw(f'!CG {CHANNEL} {GROUP}')
        time.sleep(0.3)
        self.next_id = 1

    def _reader(self):
        buf = b''
        while self.running:
            try:
                d = self.s.recv(4096)
                if not d:
                    break
                buf += d
                while b'\n' in buf:
                    raw, buf = buf.split(b'\n', 1)
                    txt = raw.decode('utf-8', 'replace').strip('\r\n ')
                    if txt:
                        with self.lock:
                            self.lines.append((time.time() - self.t0, txt))
            except socket.timeout:
                continue
            except OSError:
                break

    def since(self, idx):
        with self.lock:
            return list(self.lines[idx:])

    def mark(self):
        with self.lock:
            return len(self.lines)

    def send_raw(self, line):
        self.s.sendall((line + '\r\n').encode())

    def radio(self, text):
        self.send_raw('> ' + text)

    def _banner(self):
        m = self.mark()
        self.radio('HELLO')
        time.sleep(1.5)
        for _, ln in self.since(m):
            if 'RADIOBRIDGE' in ln:
                return ln.split(':')[3]
        return '?'

    def hello(self):
        """Session reset: expectedNext_ -> 1, clears any outstanding gap."""
        m = self.mark()
        self.radio('HELLO')
        deadline = time.time() + 3
        while time.time() < deadline:
            for _, ln in self.since(m):
                if 'robot tovez' in ln:
                    self.next_id = 1
                    return ln
            time.sleep(0.1)
        return None

    def seq(self, verb, tries=6, wait=1.2):
        """Send a SEQUENCED verb, ack-verified, retransmitting the SAME id."""
        vid = self.next_id
        pat = re.compile(r'\back %d\b' % vid)
        for attempt in range(tries):
            m = self.mark()
            self.radio(f'{verb} #{vid}')
            deadline = time.time() + wait
            while time.time() < deadline:
                for _, ln in self.since(m):
                    if pat.search(ln):
                        self.next_id = vid + 1
                        return ln, attempt
                    if ' nack ' in ln or ln.strip().startswith('< nack'):
                        self.hello()
                        vid = self.next_id
                        pat = re.compile(r'\back %d\b' % vid)
                        break
                time.sleep(0.05)
        return None, tries

    def close(self):
        self.running = False
        time.sleep(0.3)
        try:
            self.s.close()
        except OSError:
            pass


def parse_frames(lines):
    cols = list(FULL_COLS)
    out = []
    for ts, ln in lines:
        t = ln[2:].strip() if ln.startswith('< ') else ln.strip()
        if t.startswith('thdr '):
            cols = t.split()[1:]
            continue
        if not t.startswith('t '):
            continue
        parts = t.split()[1:]
        if len(parts) != len(cols):
            continue                      # fragmented / truncated frame
        try:
            vals = [int(p, 16) if c == 'flags' else int(p)
                    for c, p in zip(cols, parts)]
        except ValueError:
            continue
        row = dict(zip(cols, vals))
        row['host_t'] = ts
        out.append(row)
    return out


def main():
    """Phases are issued back-to-back, each SUPERSEDING the previous lease
    ~0.2 s early. Letting a lease EXPIRE instead stops the kernel, and the
    telemetry then republishes its last snapshot forever (MEASURED this
    session: cyc frozen at 268 while vl/vr held 174/148 for 1.6 s) -- so an
    expiry hides the deceleration behind stale data. Explicit `WHEELS_V 0 0`
    phases keep the kernel stepping, which is the only way the descent is
    real rather than a freeze.
    """
    turn_v = 150.0
    turn_ms = int(round(3.141592653589793 * TRACKWIDTH_MM / turn_v * 1000))
    phases = [
        ('zero-0',     0,             0,            1000, 0.0,     0.0),
        ('leg-150',    150,           150,          4000, 150.0,   150.0),
        ('zero-1',     0,             0,            1400, 0.0,     0.0),
        ('leg-200',    200,           200,          4000, 200.0,   200.0),
        ('zero-2',     0,             0,            1400, 0.0,     0.0),
        ('turn-360',   -int(turn_v),  int(turn_v),  turn_ms, -turn_v, turn_v),
        ('zero-3',     0,             0,            1600, 0.0,     0.0),
    ]

    s = Session()
    banner = s.hello()
    print(f'relay={s.relay} robot={banner}', flush=True)
    if not banner or 'tovez' not in banner:
        print('ABORT: HELLO did not identify tovez', file=sys.stderr)
        s.close()
        sys.exit(1)

    ack, tries = s.seq('TLM FULL')
    print(f'subscribe: {ack} (attempts={tries + 1})', flush=True)
    time.sleep(0.8)

    start_mark = s.mark()
    events = []
    for name, l, r, dur, cl, cr in phases:
        t_send = time.time() - s.t0
        ack, tries = s.seq(f'WHEELS_V {l} {r} {dur}')
        t_ack = time.time() - s.t0
        print(f'{name}: {ack} (attempts={tries + 1})', flush=True)
        if ack is None:
            print(f'ABORT: {name} never acked', file=sys.stderr)
            break
        events.append({'name': name, 'left': cl, 'right': cr,
                       'dur_ms': dur, 't_send': t_send, 't_ack': t_ack})
        # supersede slightly early so the kernel never stops stepping
        time.sleep(max(0.2, dur / 1000.0 - 0.2))
    time.sleep(0.5)
    end_mark = s.mark()

    s.seq('TLM OFF')
    lines = s.since(start_mark)[:end_mark - start_mark]
    relay = s.relay
    s.close()

    frames = parse_frames(lines)
    print(f'frames={len(frames)}', flush=True)
    out = {'robot': 'tovez', 'relay': relay, 'channel': CHANNEL,
           'trackwidth_mm': TRACKWIDTH_MM, 'turn_ms': turn_ms,
           'events': events, 'frames': frames}
    path = sys.argv[1] if len(sys.argv) > 1 else 'capture.json'
    with open(path, 'w') as fh:
        json.dump(out, fh)
    print('wrote', path, flush=True)


if __name__ == '__main__':
    main()
