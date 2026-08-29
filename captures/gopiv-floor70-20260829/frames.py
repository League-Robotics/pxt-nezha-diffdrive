"""Session to tovez over the torture mbrelay pool (radio channel 3).

Copied from captures/tovez-wheels-20260828/capture.py (Session +
parse_frames) so this capture directory is self-contained. Every
sequenced verb is ack-verified and retransmitted with its ORIGINAL id
(a fresh id is a numeric gap and stalls the v6 stream on purpose).
"""
import re
import socket
import threading
import time

HOST, PORT = '192.168.1.12', 8760
CHANNEL, GROUP, POWER = 3, 10, 7

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

    def seq(self, verb, tries=8, wait=1.5):
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

    def get(self, field, tries=6):
        """GET <field> -> float, or None. Reply line: '< ok <field> <value>'
        (whatever shape it has, the last token is the value)."""
        for _ in range(tries):
            m = self.mark()
            ack, _ = self.seq(f'GET {field}')
            if ack is None:
                continue
            deadline = time.time() + 1.0
            while time.time() < deadline:
                for _, ln in self.since(m):
                    t = ln[2:] if ln.startswith('< ') else ln
                    if field in t and not t.startswith('ack') and 'GET' not in t:
                        try:
                            return float(t.split()[-1])
                        except ValueError:
                            pass
                time.sleep(0.05)
        return None

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
