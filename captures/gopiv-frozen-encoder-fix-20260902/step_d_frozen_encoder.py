"""Step D -- ticket 001 (frozen-encoder hold) hardware acceptance on gopiv.

Adapted from captures/gopiv-profile-sweep-20260901/tight_tour.py (same
orange-dot 100x60 cm geometry, same shaping SETs, TLM FULL) -- copied
into this capture dir per the dispatch brief rather than edited in
place, and pointed at gopiv's current farm address. Runs the tour
`--reps` times back to back, accumulating TLM FULL frames across all
reps, then scans for a frozen-but-acked encoder tick (posl or posr
unchanged from the previous frame while the corresponding duty is
nonzero) and reports whether i2cf ticked on that frame and whether
duty stepped toward the rail (+-10000, i.e. +-100.00%) on that tick or
the next one.
"""
import json
import re
import socket
import sys
import threading
import time

HOST, PORT = '192.168.1.150', 43181
LEGS_MM = [1000, 600, 1000, 600]
PIVOT_MRAD = 1571
DUTY_RAIL = 10000  # dutl/dutr are duty% * 100, so +-100.00% = +-10000


class Link:
    def __init__(s, host=HOST, port=PORT):
        s.sock = socket.create_connection((host, port), timeout=10)
        s.sock.settimeout(0.1)
        s.lines = []
        s.lock = threading.Lock()
        s.run = True
        s._seq = 0
        threading.Thread(target=s._rd, daemon=True).start()
        time.sleep(0.5)

    def _rd(s):
        buf = b''
        while s.run:
            try:
                d = s.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            buf += d
            while b'\n' in buf:
                r, buf = buf.split(b'\n', 1)
                t = r.decode('utf-8', 'replace').strip()
                if t:
                    with s.lock:
                        s.lines.append(t)

    def mark(s):
        with s.lock:
            return len(s.lines)

    def since(s, i):
        with s.lock:
            return s.lines[i:]

    def send(s, line):
        s.sock.sendall((line + '\r\n').encode())

    def wait(s, mark, pat, timeout):
        rx = re.compile(pat)
        end = time.time() + timeout
        while time.time() < end:
            for l in s.since(mark):
                if rx.match(l):
                    return l
            time.sleep(0.005)
        return None

    def unseq(s, cmd, pat, timeout=1.5, tries=3):
        for _ in range(tries):
            m = s.mark(); s.send(cmd)
            got = s.wait(m, pat, timeout)
            if got:
                return got
        return None

    def seqd(s, cmd, timeout=2.0, tries=4):
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        for _ in range(tries):
            m = s.mark(); s.send(wire)
            got = s.wait(m, r'^(ack|err)\s+%d\b' % s._seq, timeout)
            if got:
                return got
        raise RuntimeError(f'no ack for {wire!r}')

    def status(s):
        return s.unseq('STATUS', r'^status ')

    def sync_seq(s):
        st = s.status()
        if st:
            m = re.search(r'\bnext=(\d+)', st)
            if m:
                s._seq = int(m.group(1)) - 1
                return s._seq
        return None

    def await_motion(s, start_timeout=3.0, idle_frames=6, timeout=40.0):
        m = s.mark()
        t0 = time.time()
        moved = False
        quiet = 0
        while time.time() - t0 < timeout:
            fr = s.frames(m)
            if fr:
                m = s.mark()
                for f in fr:
                    speed = abs(f[9]) + abs(f[10])
                    if speed > 15:
                        moved = True
                        quiet = 0
                    elif moved:
                        quiet += 1
            if moved and quiet >= idle_frames:
                return True
            if not moved and time.time() - t0 > start_timeout:
                return False
            time.sleep(0.01)
        return False

    def frames(s, i):
        out = []
        for l in s.since(i):
            p = l.split()
            if len(p) == 21 and p[0] == 't':
                try:
                    out.append([int(v) for v in p[1:]])
                except ValueError:
                    pass
        return out

    def close(s):
        try:
            s.seqd('TLM OFF')
        except Exception:
            pass
        s.run = False
        time.sleep(0.15)
        s.sock.close()


FIELDS = ['seq', 'now', 'flags', 'x', 'y', 'h', 'ox', 'oy', 'oh', 'vl', 'vr',
          'i2cf', 'cyc', 'posl', 'posr', 'dutl', 'dutr', 'lexc', 'wrng', 'cycovr']
IDX = {name: i for i, name in enumerate(FIELDS)}


def run_one_tour(l, rep, log):
    for i, leg in enumerate(LEGS_MM):
        for dist, rot in ((leg, 0), (0, PIVOT_MRAD)):
            l.seqd(f'MOVE_X {dist} {rot} 300 40000')
            if not l.await_motion():
                log(f'  rep {rep} side {i + 1}: TIMEOUT waiting for completion')
        log(f'  rep {rep} side {i + 1} ({leg / 10:.0f} cm) done')


def analyze(frames_list, log):
    """Scan for a frozen-but-acked read: posl/posr unchanged from the
    previous frame while the corresponding duty is nonzero. Report
    whether i2cf ticked on that frame, and whether duty on that tick or
    the next one stepped toward the rail relative to the tick BEFORE
    the freeze (the fix's own contract: it must not)."""
    events = []
    for i in range(1, len(frames_list)):
        prev, cur = frames_list[i - 1], frames_list[i]
        for side, pos_key, dut_key in (('L', 'posl', 'dutl'), ('R', 'posr', 'dutr')):
            pos_prev, pos_cur = prev[IDX[pos_key]], cur[IDX[pos_key]]
            dut_cur = cur[IDX[dut_key]]
            if pos_cur == pos_prev and abs(dut_cur) > 200:  # driven: >2% duty
                i2cf_prev, i2cf_cur = prev[IDX['i2cf']], cur[IDX['i2cf']]
                i2cf_ticked = i2cf_cur > i2cf_prev
                dut_before = prev[IDX[dut_key]]
                dut_next = frames_list[i + 1][IDX[dut_key]] if i + 1 < len(frames_list) else None
                stepped_toward_rail = False
                # "stepped toward the rail" -- moved measurably closer to
                # +-DUTY_RAIL on this tick or the next, relative to the
                # tick immediately before the freeze.
                for check_val, label in ((dut_cur, 'this tick'), (dut_next, 'next tick')):
                    if check_val is None:
                        continue
                    closer = abs(abs(check_val) - DUTY_RAIL) < abs(abs(dut_before) - DUTY_RAIL) - 200
                    if closer:
                        stepped_toward_rail = True
                events.append({
                    'frame_index': i, 'side': side,
                    'pos': pos_cur, 'dut_before': dut_before, 'dut_at': dut_cur,
                    'dut_next': dut_next, 'i2cf_prev': i2cf_prev, 'i2cf_cur': i2cf_cur,
                    'i2cf_ticked': i2cf_ticked, 'stepped_toward_rail': stepped_toward_rail,
                })
    return events


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out_prefix = sys.argv[2] if len(sys.argv) > 2 else 'step_d'
    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    l = Link()
    log(f'=== Step D frozen-encoder hold, {reps} reps, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
    log(f'banner: {l.unseq("HELLO", r"^device ")}')
    log(f'seq synced to robot at {l.sync_seq()}')
    for c in ('SET accel 500', 'SET decel 300', 'SET jerk 4000',
              'SET plateau_min_s 0.15', 'SET max_yaw_rate 90'):
        l.seqd(c)
    log('shaping set')

    l.seqd('TLM FULL')
    m = l.mark()
    t0 = time.time()
    for rep in range(reps):
        run_one_tour(l, rep, log)
    all_frames = l.frames(m)
    l.seqd('TLM OFF')
    wall = time.time() - t0
    log(f'wall clock {wall:.1f} s, {len(all_frames)} frames, {reps} reps')

    json.dump({'robot': 'gopiv', 'geometry': 'orange-dot 100x60 cm',
               'legs_mm': LEGS_MM, 'reps': reps, 'wall_s': wall,
               'frames': all_frames, 'fields': FIELDS},
              open(f'{out_prefix}_frames.json', 'w'))

    events = analyze(all_frames, log)
    log(f'\nfrozen-but-driven-encoder events found: {len(events)}')
    for e in events:
        log(f'  frame {e["frame_index"]} side {e["side"]}: pos={e["pos"]} '
            f'dut_before={e["dut_before"]} dut_at={e["dut_at"]} dut_next={e["dut_next"]} '
            f'i2cf {e["i2cf_prev"]}->{e["i2cf_cur"]} ticked={e["i2cf_ticked"]} '
            f'stepped_toward_rail={e["stepped_toward_rail"]}')

    n_i2cf_ticked = sum(1 for e in events if e['i2cf_ticked'])
    n_stepped = sum(1 for e in events if e['stepped_toward_rail'])
    log(f'\nsummary: {len(events)} frozen-driven events, '
        f'{n_i2cf_ticked} with i2cf tick, {n_stepped} with duty stepping toward rail')

    with open(f'{out_prefix}_notes_auto.txt', 'w') as f:
        f.write('\n'.join(log_lines) + '\n')

    l.close()


if __name__ == '__main__':
    main()
