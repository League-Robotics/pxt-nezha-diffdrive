"""run_tour -- execute a .tour on hardware and chart it.

Produces the standard two-panel review chart: the X-Y path on the left,
wheel speeds against time on the right.

    uv run python tests/system/run_tour.py tests/system/tours/square.tour
    uv run python tests/system/run_tour.py .../infinity.tour --open

Connects over a farm node's serial daemon (lossless TCP) by default, or a
local USB port with --port. Completion is detected from the TELEMETRY
STREAM, never from the `done`/`next` counters: `done` is cumulative and
survives HELLO, so an absolute test against it passes instantly on a
fresh session and silently preempts each in-flight move with the next
command (measured 2026-09-01 -- an entire 100 cm leg vanished that way).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tourfile import parse_tour, Twist, Dwell, SetCfg   # noqa: E402

DEFAULT_HOST, DEFAULT_PORT = '192.168.1.147', 0   # 0 => discover


def discover_port(host, want_name=None):
    """Find the serial daemon's port for a robot.

    The daemon binds a DYNAMIC port per board, so it moves between
    sessions; hardcoding one guarantees a ConnectionRefused later. Ask
    the host which ports it is listening on, then probe each with an
    unsequenced ID until a diffdrive answers.
    """
    out = subprocess.run(
        ['ssh', '-o', 'ConnectTimeout=8', f'eric@{host}',
         "sudo ss -tlnp 2>/dev/null | grep python3 || true"],
        capture_output=True, text=True, timeout=30).stdout
    ports = sorted({int(m.group(1))
                    for m in re.finditer(r'0\.0\.0\.0:(\d+)', out)})
    for port in ports:
        try:
            sk = socket.create_connection((host, port), timeout=4)
            sk.settimeout(0.4)
            sk.sendall(b'ID\r\n')
            buf, end = b'', time.time() + 2
            while time.time() < end:
                try:
                    buf += sk.recv(4096)
                except socket.timeout:
                    pass
            sk.close()
            txt = buf.decode('utf-8', 'replace')
            if 'id diffdrive' in txt:
                if want_name and want_name not in txt:
                    continue
                print(f'  discovered {txt.strip().splitlines()[0]} on port {port}')
                return port
        except OSError:
            continue
    raise SystemExit(f'no diffdrive serial daemon found on {host} '
                     f'(checked ports {ports})')
TRAVEL_CALIB = 0.7878
CPM = 10.0 / TRAVEL_CALIB          # counts per mm


class Link:
    """v6 wire over a TCP serial daemon, with a draining reader thread."""

    def __init__(s, host=DEFAULT_HOST, port=DEFAULT_PORT):
        s.sock = socket.create_connection((host, port), timeout=10)
        s.sock.settimeout(0.1)
        s.lines, s.lock, s.run, s._seq = [], threading.Lock(), True, 0
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

    def await_motion(s, start_timeout=4.0, idle_frames=6, timeout=60.0):
        """Wait by watching wheel speed, not a counter (see module doc)."""
        m, t0 = s.mark(), time.time()
        moved, quiet = False, 0
        while time.time() - t0 < timeout:
            fr = s.frames(m)
            if fr:
                m = s.mark()
                for f in fr:
                    if abs(f[9]) + abs(f[10]) > 15:
                        moved, quiet = True, 0
                    elif moved:
                        quiet += 1
            if moved and quiet >= idle_frames:
                return True
            if not moved and time.time() - t0 > start_timeout:
                return False
            time.sleep(0.01)
        return False

    def close(s):
        try:
            s.seqd('TLM OFF')
        except Exception:
            pass
        s.run = False
        time.sleep(0.15)
        s.sock.close()


def execute(tour, link, warmup=0, cruise_scale=1.0):
    print(f'tour {tour.name}: {len(tour.steps)} steps', flush=True)
    banner = link.unseq('HELLO', r'^device ')
    print(f'  {banner}', flush=True)
    link._seq = 0

    if warmup:
        link.seqd('TLM FULL')
        for _ in range(warmup):
            link.seqd('MOVE_X 0 1571 300 20000')
            time.sleep(2.3)
        link.seqd('TLM OFF')
        print(f'  warmed up ({warmup} pivots)', flush=True)

    link.seqd('TLM FULL')
    mark = link.mark()
    t0 = time.time()
    segments = []
    for i, step in enumerate(tour.steps, 1):
        if isinstance(step, SetCfg):
            link.seqd(f'SET {step.field_name} {step.value}')
            print(f'  set {step.field_name} = {step.value}', flush=True)
            continue
        if isinstance(step, Dwell):
            time.sleep(step.seconds)
            continue
        cruise = max(1, int(round(step.cruise_mm_s * cruise_scale)))
        start = time.time() - t0
        link.seqd(f'MOVE_X {int(round(step.dist_mm))} '
                  f'{int(round(step.rot_mrad))} {cruise} '
                  f'{int(step.timeout_s * 1000)}')
        ok = link.await_motion(timeout=step.timeout_s + 10)
        segments.append({'n': i, 'kind': step.kind, 'mark': step.mark,
                         'dist_mm': step.dist_mm, 'rot_mrad': step.rot_mrad,
                         'cruise': cruise, 't0': start, 't1': time.time() - t0,
                         'completed': ok})
        tag = step.mark or step.kind
        print(f'  [{i:3d}/{len(tour.steps)}] {tag:12s} '
              f'dist {step.dist_mm:7.1f} rot {step.rot_mrad:8.1f} '
              f'{"ok" if ok else "TIMEOUT"}', flush=True)
    time.sleep(0.8)
    frames = link.frames(mark)
    link.seqd('TLM OFF')
    return frames, segments, time.time() - t0


def chart(tour_name, frames, segments, wall, out_png, subtitle=''):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fr = np.array(frames, float)
    if len(fr) < 5:
        print('  too few telemetry frames to chart'); return None
    t = (fr[:, 1] - fr[0, 1]) / 1000.0
    x, y = fr[:, 3] / 10.0, fr[:, 4] / 10.0        # mm -> cm
    vl, vr = fr[:, 9], fr[:, 10]
    x, y = x - x[0], y - y[0]
    closure = math.hypot(x[-1], y[-1]) * 10.0      # mm

    BLUE, ORANGE = '#2a78d6', '#d95926'
    INK, MUT, GRID = '#0b0b0b', '#52514e', '#e4e2dc'
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.0, 5.6), facecolor='#faf9f5')
    for ax in (ax1, ax2):
        ax.set_facecolor('#faf9f5')
        for sp in ('top', 'right'):
            ax.spines[sp].set_visible(False)
        for sp in ('left', 'bottom'):
            ax.spines[sp].set_color(GRID)
        ax.tick_params(colors=MUT, labelsize=9)
        ax.grid(True, color=GRID, linewidth=0.7)

    ax1.plot(x, y, color=BLUE, linewidth=1.7)
    ax1.plot(0, 0, 'o', color=INK, markersize=9, zorder=6)
    ax1.plot(x[-1], y[-1], 'o', color=ORANGE, markersize=7, zorder=6)
    ax1.annotate(f'closure {closure:.1f} mm', (x[-1], y[-1]),
                 textcoords='offset points', xytext=(9, 8), color=MUT, fontsize=9)
    ax1.set_aspect('equal'); ax1.margins(0.15)
    ax1.set_xlabel('x [cm]', color=MUT); ax1.set_ylabel('y [cm]', color=MUT)
    nseg = len([s for s in segments if s['kind'] != 'dwell'])
    ax1.set_title(f'Odometry path — {nseg} segments', color=INK,
                  fontsize=10.5, loc='left')

    ax2.plot(t, vl, color=BLUE, linewidth=1.2)
    ax2.plot(t, vr, color=ORANGE, linewidth=1.2)
    ax2.legend(['left wheel', 'right wheel'], frameon=False, labelcolor=MUT,
               fontsize=9, loc='upper right')
    ax2.set_xlabel('time [s]', color=MUT)
    ax2.set_ylabel('wheel speed [mm/s]', color=MUT)
    ax2.set_title(f'Wheel speeds — {len(fr)} frames, {wall:.1f} s',
                  color=INK, fontsize=10.5, loc='left')

    head = f'{tour_name} — {time.strftime("%Y-%m-%d")}'
    fig.suptitle(head + (f'\n{subtitle}' if subtitle else ''),
                 color=INK, fontsize=12, x=0.02, ha='left')
    fig.tight_layout(rect=(0, 0, 1, 0.93 if subtitle else 0.95))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    return closure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tour')
    ap.add_argument('--host', default=DEFAULT_HOST)
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--robot', default=None, help='name to match during discovery')
    ap.add_argument('--warmup', type=int, default=0)
    ap.add_argument('--cruise-scale', type=float, default=1.0)
    ap.add_argument('--out', default=None)
    ap.add_argument('--open', action='store_true')
    a = ap.parse_args()

    tour = parse_tour(a.tour)
    port = a.port or discover_port(a.host, a.robot)
    time.sleep(1.0)          # let the daemon release the discovery socket
    for attempt in range(3):
        try:
            link = Link(a.host, port)
            break
        except OSError as exc:
            if attempt == 2:
                raise
            print(f'  connect retry after {exc}')
            time.sleep(2.0)
    try:
        frames, segments, wall = execute(tour, link, a.warmup, a.cruise_scale)
    finally:
        link.close()

    # --out takes either a .png path or a DIRECTORY to drop <tour>.png
    # into. Accepting the directory form matters more than it looks:
    # passing one used to sail past the "save before charting" guard
    # below (the .json path came out as a directory too) and threw away
    # a completed 16-arc run -- the one thing that guard exists to
    # prevent. MEASURED 2026-09-01, spline.tour on gopiv.
    out = a.out or f'reports/tours-{time.strftime("%Y%m%d")}/{tour.name}.png'
    if not out.endswith('.png'):
        out = str(Path(out) / f'{tour.name}.png')
    sub = (f'{len(segments)} moves, {wall:.1f} s wall clock '
           f'(bench, pure odometry)')
    # Save the run BEFORE charting: a plotting error must never cost the
    # hardware data, which is the expensive half.
    data = out.replace('.png', '.json')
    Path(data).parent.mkdir(parents=True, exist_ok=True)
    json.dump({'tour': tour.name, 'source': tour.source, 'wall_s': wall,
               'segments': segments, 'frames': frames}, open(data, 'w'))
    closure = chart(tour.name, frames, segments, wall, out, sub)
    print(f'\nclosure {closure:.1f} mm' if closure is not None else '\nno chart')
    print(f'chart {out}\ndata  {data}')
    if a.open:
        subprocess.run(['open', out], check=False)


if __name__ == '__main__':
    main()
