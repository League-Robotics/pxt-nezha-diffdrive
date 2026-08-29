"""Legs-and-turn sequence on gopiv over the mbdeploy farm (raw TCP), N runs.

    python3 run_seq.py <label> <n_runs> out.json

Per run: MOVE_X 600 @150 (4 s), MOVE_X 800 @200 (4 s), MOVE_X 0 6283 @150
(360 deg CCW) -- the 2026-08-28 "first test" (4 s at 150, 4 s at 200, then
a 360) re-expressed as distance moves so each leg has MOVE_X's taper and
end-of-move behaviour. Completion from telemetry with the 0.7 s grace
re-check (never a fixed sleep). TLM FULL frames + event log -> JSON.
gopiv is a bench rig (bare motors, no wheels: radio-robot-lib
config/robots/gopiv.json) -- there is no surface to fall off.
"""
import json
import socket
import sys
import time

from frames import parse_frames

HOST = '192.168.1.148'
FIELDS = 'pid_kp pid_ki pid_i_max speed_floor pos_err_max crawl_pulse twist_hold_gain'.split()


def resolve_port():
    """The daemon's per-board serial port is dynamic (33059 on 2026-08-29,
    never hard-code). Resolve the _mbserial._tcp record with macOS dns-sd
    (it never exits on its own, so kill it after a few seconds); fall back
    to the last port mbdeploy printed for gopiv."""
    import subprocess, re
    try:
        p = subprocess.run(['dns-sd', '-L', 'gopiv', '_mbserial._tcp', 'local.'],
                           capture_output=True, text=True, timeout=4)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or '')
    m = re.search(r'can be reached at \S+:(\d+)', out)
    if m:
        return int(m.group(1))
    print('dns-sd gave no port, falling back to 33059', flush=True)
    return 33059


class Tcp:
    def __init__(self, host, port):
        import threading, re
        self.re = re
        self.s = socket.create_connection((host, port), timeout=10)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.s.settimeout(0.2)
        self.lines, self.lock, self.running = [], threading.Lock(), True
        self.t0, self.next_id = time.time(), 1
        self.rx = threading.Thread(target=self._reader, daemon=True); self.rx.start()
        time.sleep(0.3)

    def _reader(self):
        buf = b''
        while self.running:
            try:
                d = self.s.recv(4096)
                if not d: break
                buf += d
                while b'\n' in buf:
                    raw, buf = buf.split(b'\n', 1)
                    txt = raw.decode('utf-8', 'replace').strip('\r\n ')
                    if txt:
                        with self.lock: self.lines.append((time.time() - self.t0, txt))
            except socket.timeout: continue
            except OSError: break

    def mark(self):
        with self.lock: return len(self.lines)
    def since(self, i):
        with self.lock: return list(self.lines[i:])
    def radio(self, text): self.s.sendall((text + '\n').encode())

    def hello(self):
        m = self.mark(); self.radio('HELLO'); dl = time.time() + 3
        while time.time() < dl:
            for _, ln in self.since(m):
                if 'robot gopiv' in ln: self.next_id = 1; return ln
            time.sleep(0.1)
        return None

    def seq(self, verb, tries=6, wait=1.5):
        vid = self.next_id; pat = self.re.compile(r'\back %d\b' % vid)
        for attempt in range(tries):
            m = self.mark(); self.radio(f'{verb} #{vid}'); dl = time.time() + wait
            while time.time() < dl:
                for _, ln in self.since(m):
                    if pat.search(ln): self.next_id = vid + 1; return ln, attempt
                time.sleep(0.05)
        return None, tries

    def get(self, field):
        for _ in range(4):
            m = self.mark(); ack, _ = self.seq(f'GET {field}')
            if ack is None: continue
            dl = time.time() + 1.0
            while time.time() < dl:
                for _, ln in self.since(m):
                    p = ln.split()
                    if len(p) == 3 and p[0] == 'get' and p[1] == field:
                        return float(p[2])
                time.sleep(0.05)
        return None

    def close(self):
        self.running = False; time.sleep(0.3)
        try: self.s.close()
        except OSError: pass


def latest(s, n=40):
    return parse_frames(s.since(0)[-n:])


def wait_done(s, t_ack, min_dur, wall=25.0):
    last_cyc, last_cyc_t, dl = None, time.time(), time.time() + wall
    while time.time() < dl:
        time.sleep(0.15)
        fr = latest(s)
        if not fr: continue
        r = fr[-1]
        if last_cyc is None or r['cyc'] != last_cyc: last_cyc, last_cyc_t = r['cyc'], time.time()
        if time.time() - s.t0 - t_ack < min_dur: continue
        quiet, pc = 0, None
        for f in fr[-10:]:
            lv = pc is None or f['cyc'] > pc; pc = f['cyc']
            if lv and abs(f['vl']) <= 20 and abs(f['vr']) <= 20: quiet += 1
            elif lv: quiet = 0
        if quiet >= 5:
            time.sleep(0.7)
            if any(abs(f['vl']) > 20 or abs(f['vr']) > 20 for f in latest(s, 12)[-6:]): continue
            return 'still'
        if time.time() - last_cyc_t > 0.8: return 'frozen'
    raise RuntimeError('move did not finish')


def move(s, verb, min_dur, events, tag):
    t_send = time.time() - s.t0
    ack, tries = s.seq(verb)
    t_ack = time.time() - s.t0
    if ack is None: raise RuntimeError('never acked: ' + verb)
    how = wait_done(s, t_ack, min_dur)
    events.append({'verb': verb, 't_send': t_send, 't_ack': t_ack, 'done_via': how,
                   'attempts': tries + 1, **tag})
    print(f'  {verb:24s} {ack.strip():16s} tries={tries+1} {how}', flush=True)


def main():
    label, n_runs, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    port = resolve_port()
    s = Tcp(HOST, port)
    print('HELLO ->', s.hello(), flush=True)
    cfg = {f: s.get(f) for f in FIELDS}
    print('config:', cfg, flush=True)
    print('TLM FULL ->', s.seq('TLM FULL')[0], flush=True); time.sleep(0.8)
    start = s.mark(); events = []
    for verb in ('MOVE_X 40 0 150 6000', 'MOVE_X -40 0 150 6000') * 2:
        move(s, verb, 0.5, events, {'phase': 'warmup', 'run': 0})
    time.sleep(1.0)
    for run in range(1, n_runs + 1):
        print(f'== {label} run {run}', flush=True)
        move(s, 'MOVE_X 600 0 150 10000', 3.0, events, {'phase': 'leg150', 'run': run})
        time.sleep(1.0)
        move(s, 'MOVE_X 800 0 200 10000', 3.0, events, {'phase': 'leg200', 'run': run})
        time.sleep(1.0)
        move(s, 'MOVE_X 0 6283 150 10000', 1.5, events, {'phase': 'turn360', 'run': run})
        time.sleep(1.5)
    end = s.mark(); s.seq('TLM OFF')
    frames = parse_frames(s.since(start)[:end - start])
    s.close()
    json.dump({'robot': 'gopiv', 'label': label, 'port': port, 'config': cfg,
               'events': events, 'frames': frames}, open(out, 'w'))
    print(f'frames={len(frames)} events={len(events)} wrote {out}', flush=True)


if __name__ == '__main__':
    main()
