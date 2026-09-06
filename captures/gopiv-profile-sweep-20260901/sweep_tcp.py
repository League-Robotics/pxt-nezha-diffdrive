"""Tier-2 profile sweep over a farm-node serial daemon (TCP, lossless).

Measures what the robot's wheels ACTUALLY do: peak speed reached, the
acceleration ramp, the deceleration slope, how much distance braking
consumes, and how fast it is still moving when the move ends. The
deceleration figure is the constant sprint 025 needs and the one thing
simulation cannot supply.

Also watches for a dead drive channel (speed stuck at 0 while duty
saturates), the fault gopiv showed on 2026-08-31.
"""
import argparse, json, re, sys, time, socket

HOST, PORT = '192.168.1.147', 38493
TRAVEL_CALIB = 0.7878          # engine default mm/deg
CPM = 10.0 / TRAVEL_CALIB      # counts per mm


class Link:
    def __init__(s, host=HOST, port=PORT):
        s.sock = socket.create_connection((host, port), timeout=10)
        s.sock.settimeout(0.15)
        s.buf = b''
        s.lines = []
        s._seq = 0
        s.pump(0.6)

    def pump(s, sec):
        end = time.time() + sec
        while time.time() < end:
            try:
                d = s.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            s.buf += d
            while b'\n' in s.buf:
                r, s.buf = s.buf.split(b'\n', 1)
                t = r.decode('utf-8', 'replace').strip()
                if t:
                    s.lines.append(t)

    def mark(s):
        return len(s.lines)

    def since(s, i):
        return s.lines[i:]

    def send(s, line):
        s.sock.sendall((line + '\r\n').encode())

    def unseq(s, cmd, pat, sec=2.5, tries=3):
        for _ in range(tries):
            m = s.mark(); s.send(cmd); s.pump(sec)
            for l in s.since(m):
                if re.match(pat, l):
                    return l
        return None

    def seqd(s, cmd, sec=3.0, tries=4):
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        pat = re.compile(r'^(ack|err)\s+%d\b' % s._seq)
        for _ in range(tries):
            m = s.mark(); s.send(wire); s.pump(sec)
            for l in s.since(m):
                if pat.match(l):
                    return l
            st = s.status()
            if st:
                mm = re.search(r'\bnext=(\d+)', st)
                if mm and int(mm.group(1)) > s._seq:
                    return st
        raise RuntimeError(f'no ack for {wire!r}')

    def hello(s):
        l = s.unseq('HELLO', r'^device ')
        s._seq = 0
        return l

    def status(s):
        return s.unseq('STATUS', r'^status ', sec=2.0, tries=2)

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

    def leg(s, dist_mm, cruise):
        s.seqd('TLM FULL')
        m = s.mark()
        timeout = max(15000, int(abs(dist_mm) * 25) + 4000)
        s.seqd(f'MOVE_X {int(dist_mm)} 0 {int(cruise)} {timeout}')
        want = s._seq
        t0 = time.time()
        while time.time() - t0 < 25:
            st = s.status()
            if st:
                mm = re.search(r'\bdone=(\d+)', st)
                if mm and int(mm.group(1)) >= want:
                    break
            s.pump(0.15)
        s.pump(0.8)
        fr = s.frames(m)
        s.seqd('TLM OFF')
        return fr

    def close(s):
        try:
            s.seqd('TLM OFF')
        except Exception:
            pass
        s.sock.close()


def fit(fr):
    if len(fr) < 6:
        return None
    # Trim to the MOTION window: telemetry keeps streaming while the
    # robot sits still before and after the move, and a trailing run of
    # zeros makes any decel fit meaningless.
    sp = [abs(0.5 * (f[9] + f[10])) for f in fr]
    moving = [i for i, x in enumerate(sp) if x > 8]
    if len(moving) < 4:
        return None
    fr = fr[moving[0]:moving[-1] + 2]
    now = [f[1] for f in fr]
    vl = [f[9] for f in fr]
    vr = [f[10] for f in fr]
    dutl = [f[15] for f in fr]
    dutr = [f[16] for f in fr]
    v = [0.5 * (a + b) for a, b in zip(vl, vr)]
    pos = [0.5 * (f[13] + f[14]) / CPM for f in fr]
    # robust peak: encoder glitches produce single-frame spikes
    # (observed 1891 mm/s on a 400 mm/s leg), so use a high quantile
    srt = sorted(abs(x) for x in v)
    pk = srt[int(0.92 * (len(srt) - 1))]
    if pk < 5:
        return None
    t = [(x - now[0]) / 1000.0 for x in now]
    i_pk = min(i for i in range(len(v)) if abs(v[i]) >= 0.98 * pk)
    accel = (abs(v[i_pk]) - abs(v[0])) / max(t[i_pk] - t[0], 1e-3)
    last90 = max(i for i in range(len(v)) if abs(v[i]) >= 0.9 * pk)
    # least-squares slope of |v| over the braking tail (peak -> end),
    # which is robust to the floor crawl the taper ends on
    xs = t[last90:]
    ys = [abs(x) for x in v[last90:]]
    dec = None
    if len(xs) >= 3:
        n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
        den = sum((x-mx)**2 for x in xs)
        if den > 1e-9:
            dec = -sum((x-mx)*(y-my) for x, y in zip(xs, ys))/den
    # dead-channel watch: one side never moves while its duty is large
    dead = None
    if max(abs(x) for x in vl) < 5 and max(abs(x) for x in dutl) > 500:
        dead = 'LEFT'
    if max(abs(x) for x in vr) < 5 and max(abs(x) for x in dutr) > 500:
        dead = 'RIGHT' if dead is None else 'BOTH'
    return {
        'peak': round(pk, 1),
        'accel': round(accel),
        'decel': round(dec) if dec else None,
        'ticks_decel': len(v) - 1 - last90,
        'brake_mm': round(abs(pos[-1] - pos[last90]), 1),
        'v_end': round(abs(v[-1]), 1),
        'travel_mm': round(abs(pos[-1] - pos[0]), 1),
        'frames': len(fr),
        'dead_channel': dead,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dist', type=float, default=300.0)
    ap.add_argument('--speeds', default='100,200,300,400')
    ap.add_argument('--out', default='sweep_gopiv.json')
    a = ap.parse_args()

    l = Link()
    print('banner:', l.hello())
    st = l.status()
    print('status:', st)
    if not st:
        print('no STATUS -- brick likely unpowered; aborting'); l.close(); return

    res = {'robot': 'gopiv', 'dist_mm': a.dist, 'runs': []}
    print(f'\n{a.dist:.0f} mm legs, alternating direction\n')
    print(' cruise |  peak | accel | decel | ticks | brake_mm | v_end | travel | dead')
    print('--------+-------+-------+-------+-------+----------+-------+--------+-----')
    sign = 1
    for c in [int(x) for x in a.speeds.split(',')]:
        fr = l.leg(sign * a.dist, c)
        sign = -sign
        m = fit(fr)
        if not m:
            print(f' {c:6d} |  no usable telemetry ({len(fr)} frames)')
            continue
        res['runs'].append({'cruise': c, **m})
        print(f" {c:6d} | {m['peak']:5.0f} | {m['accel']:5} | {str(m['decel']):>5} |"
              f" {m['ticks_decel']:5} | {m['brake_mm']:8.1f} | {m['v_end']:5.0f} |"
              f" {m['travel_mm']:6.1f} | {m['dead_channel'] or '-'}")
        time.sleep(0.5)

    json.dump(res, open(a.out, 'w'), indent=1)
    print(f'\nsaved {a.out}')
    l.close()


if __name__ == '__main__':
    main()
