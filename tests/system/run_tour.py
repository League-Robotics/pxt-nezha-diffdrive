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
from tourfile import parse_tour, Twist, Dwell, SetCfg, Spline   # noqa: E402

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

    def seq_fire(s, cmd):
        """Send a sequenced verb WITHOUT waiting for its ack.

        For a control loop only. `seqd()` blocks up to 2 s for an ack,
        and a live TLM stream starves inbound acks, so waiting turns a
        120 ms pursuit period into something far longer and the
        follower falls behind the robot. Ids still increment in order,
        which is what the robot's `expectedNext_` requires; the link is
        a lossless TCP daemon, so a dropped line (which would stall the
        stream on a gap) is not the failure mode here.
        """
        s._seq += 1
        s.send(f'{cmd} #{s._seq}')

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

    def pose(s):
        """Latest odometry pose as (x_mm, y_mm, heading_rad), or None.

        Reads the tail of the telemetry stream rather than asking, so
        it costs nothing and cannot stall the control loop behind a
        request/reply round trip. `h` is CUMULATIVE centidegrees, so it
        is wrapped here and nowhere else.
        """
        with s.lock:
            tail = s.lines[-40:]
        for l in reversed(tail):
            p = l.split()
            if len(p) == 21 and p[0] == 't':
                try:
                    # p[0] is the 't' tag, so the 20 payload columns start
                    # at p[1]: seq now flags x y h ... -- x is p[4], NOT
                    # p[3]. frames() strips the tag first and is indexed
                    # one lower throughout; mixing the two conventions
                    # returned (flags, x, y) here and read as a pose that
                    # barely moved (a 91.25 deg pivot measured as 0.02).
                    return (float(p[4]), float(p[5]),
                            math.radians(float(p[6]) / 100.0))
                except ValueError:
                    continue
        return None

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
        if isinstance(step, Spline):
            start = time.time() - t0
            src = Path(tour.source).parent / step.path
            print(f'  [{i:3d}/{len(tour.steps)}] spline {step.path} '
                  f'speed {step.speed:.0f} lookahead {step.lookahead:.0f} '
                  f'laps {step.laps}', flush=True)
            errs, laps, ref = pure_pursuit(
                link, Spline(str(src), step.speed, step.lookahead,
                             step.laps, step.interval, step.mark), mark)
            import statistics
            segments.append({
                'n': i, 'kind': 'spline', 'mark': step.mark,
                'path': step.path, 'speed': step.speed,
                'lookahead': step.lookahead, 'laps_done': laps,
                'xtrack_mean_mm': statistics.fmean(errs) if errs else None,
                'xtrack_max_mm': max(errs) if errs else None,
                'xtrack_p95_mm': (sorted(errs)[int(len(errs) * 0.95)]
                                  if errs else None),
                't0': start, 't1': time.time() - t0, 'completed': laps > 0.98,
                'reference_cm': ref})
            print(f'        cross-track mean '
                  f'{segments[-1]["xtrack_mean_mm"]:.1f} mm  p95 '
                  f'{segments[-1]["xtrack_p95_mm"]:.1f}  max '
                  f'{segments[-1]["xtrack_max_mm"]:.1f}  '
                  f'({laps:.2f} laps)', flush=True)
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


class Path2D:
    """A fitted path, as a densely sampled polyline with arc length.

    The `.path.json` files carry `points` in mm in the field frame plus
    `closed`, `length_mm` and `min_radius_mm`. Pure pursuit only needs
    the polyline and a way to walk forward along it.
    """

    def __init__(s, path_json):
        d = json.loads(Path(path_json).read_text())
        s.name = d.get('name', Path(path_json).stem)
        s.closed = bool(d.get('closed', False))
        s.min_radius = d.get('min_radius_mm')
        s.pts = [(float(a), float(b)) for a, b in d['points']]
        if s.closed and s.pts[0] != s.pts[-1]:
            s.pts.append(s.pts[0])
        s.cum = [0.0]
        for i in range(1, len(s.pts)):
            s.cum.append(s.cum[-1] + math.dist(s.pts[i - 1], s.pts[i]))
        s.length = s.cum[-1]

    def at(s, dist):
        """The point at arc length `dist`, wrapping if the path closes."""
        if s.closed:
            dist %= s.length
        dist = min(max(dist, 0.0), s.length)
        lo, hi = 0, len(s.cum) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if s.cum[mid] <= dist:
                lo = mid
            else:
                hi = mid
        span = s.cum[lo + 1] - s.cum[lo]
        f = 0.0 if span <= 0 else (dist - s.cum[lo]) / span
        (x0, y0), (x1, y1) = s.pts[lo], s.pts[lo + 1]
        return x0 + f * (x1 - x0), y0 + f * (y1 - y0)

    def nearest(s, x, y, near_dist, window=400.0):
        """Arc length of the closest point, searched only NEAR `near_dist`.

        A global nearest-point search is wrong for pure pursuit on a
        path that crosses or doubles back: it can snap to a far-away
        branch that happens to be closer in space, and the robot then
        cuts across the figure. Searching a window around where the
        robot already was keeps progress monotone.
        """
        best, best_d2 = near_dist, float('inf')
        steps = 160
        for i in range(steps + 1):
            probe = near_dist - window * 0.25 + window * i / steps
            px, py = s.at(probe)
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 < best_d2:
                best, best_d2 = probe, d2
        return best, math.sqrt(best_d2)


def pure_pursuit(link, step, out_frames_mark, log=print):
    """Follow `step.path` with pure pursuit, closing the loop on odometry.

    The loop the stakeholder described: walk the spline with a circle,
    take the point where the circle leaves the path ahead of the robot,
    and drive at that point -- over and over.

    Each iteration:
      1. read the robot's pose from the telemetry stream
      2. advance the arc-length cursor to the nearest point on the path
      3. aim at the point one lookahead further along
      4. convert that to a curvature and command it with MOVE_V

    Curvature comes from the standard pure-pursuit geometry: with the
    aim point at (dx, dy) in the robot's frame and |aim| = L,

        kappa = 2 * dy / L^2        [1/mm]
        omega = kappa * v           [rad/s]

    MOVE_V takes a body speed and a yaw RATE and holds them for a
    duration, so the robot keeps moving between host updates instead of
    stopping at every waypoint. Commanding discrete MOVE_X hops to each
    aim point would also "drive to the point over and over", but it
    would stop and re-accelerate every cycle -- a stutter, not a
    followed curve.

    Returns (cross_track_samples, laps_completed).
    """
    path = Path2D(Path(step.path))
    pose = link.pose()
    if pose is None:
        raise RuntimeError('no telemetry pose -- is TLM FULL running?')

    # The path is authored in the FIELD frame; the robot is wherever it
    # is, in its own inherited odometry frame. Anchor the path to the
    # pose the robot starts from -- the same start-frame convention the
    # charts use -- so the follower is not chasing a coordinate system
    # the robot has never been in.
    #
    # Align the path's INITIAL TANGENT with the robot's heading, not the
    # path's +x axis. complex.path.json leaves its first point heading
    # almost due +y, so anchoring on the axis instead started the robot
    # 90 deg off the path and it spent the first lobe swerving back on:
    # MEASURED 2026-09-01, cross-track mean 65.0 mm / max 307.1 that way.
    x0, y0, h0 = pose
    px0, py0 = path.at(0.0)
    tx, ty = path.at(min(20.0, path.length * 0.01))
    tangent0 = math.atan2(ty - py0, tx - px0)
    rot = h0 - tangent0
    ca, sa = math.cos(rot), math.sin(rot)

    def to_odom(px, py):
        u, v = px - px0, py - py0
        return x0 + u * ca - v * sa, y0 + u * sa + v * ca

    total = path.length * step.laps
    cursor, errs, t0 = 0.0, [], time.time()
    dur_ms = int(step.interval * 1000 * 2.2)   # outlive one period
    deadline = t0 + total / max(step.speed, 1.0) * 3.0 + 30.0

    while cursor < total - step.lookahead * 0.5:
        if time.time() > deadline:
            log('  pure pursuit: deadline exceeded, stopping')
            break
        pose = link.pose()
        if pose is None:
            time.sleep(step.interval)
            continue
        rx, ry, rh = pose

        # Where are we on the path? Search near the cursor, not globally.
        lap_base = math.floor(cursor / path.length) * path.length
        local = cursor - lap_base
        # The path is in field coords; compare in field coords too.
        u = (rx - x0) * ca + (ry - y0) * sa
        v = -(rx - x0) * sa + (ry - y0) * ca
        fx, fy = px0 + u, py0 + v      # ca/sa carry `rot`, not h0
        local, err = path.nearest(fx, fy, local)
        errs.append(err)
        cursor = lap_base + local

        ax, ay = path.at(local + step.lookahead)
        ax, ay = to_odom(ax, ay)
        dx, dy = ax - rx, ay - ry
        # Into the robot's frame.
        fwd = dx * math.cos(rh) + dy * math.sin(rh)
        lat = -dx * math.sin(rh) + dy * math.cos(rh)
        L2 = dx * dx + dy * dy
        kappa = 2.0 * lat / L2 if L2 > 1.0 else 0.0

        v_cmd = step.speed
        if fwd < 0:
            # Aim point is behind us: turn toward it rather than
            # reversing into the path.
            v_cmd = step.speed * 0.35
        omega = kappa * v_cmd                      # [rad/s]
        link.seq_fire(f'MOVE_V {int(round(v_cmd))} '
                      f'{int(round(omega * 1000.0))} {dur_ms}')
        time.sleep(step.interval)

    link.seq_fire('MOVE_V 0 0 200')
    time.sleep(0.4)
    try:
        link.seqd('STOP')
    except RuntimeError:
        pass

    c2, s2 = math.cos(-tangent0), math.sin(-tangent0)
    ref = []
    n = max(2, int(path.length / 5.0))
    for i in range(n + 1):
        gx, gy = path.at(path.length * i / n)
        u, v = gx - px0, gy - py0
        ref.append(((u * c2 - v * s2) / 10.0, (u * s2 + v * c2) / 10.0))
    return errs, cursor / path.length, ref


def start_frame(x, y, h_centideg):
    """Re-express an odometry track in the frame the TOUR starts in.

    Translates to the start position AND rotates so the robot's initial
    heading points along +x. Both halves matter, and the rotation is
    the one that is easy to leave out.

    The robot's odometry frame is whatever it was when the program last
    booted; nothing on the wire can rebase it (see
    `clasi/issues/no-wire-verb-reaches-rebaseposition-so-tours-cannot-
    zero-their-frame.md`), so a tour run after other tours starts at an
    arbitrary pose in an inherited frame. MEASURED gopiv 2026-09-01,
    `reports/tours-20260901/square.json`: the square tour began at
    (-1154, -208) mm with a cumulative heading of 4909.66 deg
    (= 229.66 deg mod 360), and its first leg travelled at -130.19 deg
    -- the same direction. Plotted raw, that perfect square renders as
    a **diamond**, and the diamond is an artifact of the frame, not
    something the robot drove.

    A tour's geometry is defined relative to where it starts, so that
    is the frame to judge it in.
    """
    import numpy as np
    x, y = np.asarray(x) - x[0], np.asarray(y) - y[0]
    a = -math.radians(h_centideg[0] / 100.0)
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def chart(tour_name, frames, segments, wall, out_png, subtitle='',
          reference=None):
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
    x, y = start_frame(x, y, fr[:, 5])
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

    if reference:
        # The curve the follower was TRACKING, in the same start frame.
        # Without it a spline chart shows a plausible squiggle and no way
        # to tell a good run from a bad one.
        rx = [q[0] for q in reference]
        ry = [q[1] for q in reference]
        ax1.plot(rx, ry, color=MUT, linewidth=1.1, linestyle=(0, (4, 3)),
                 zorder=2, label='reference path')
    ax1.plot(x, y, color=BLUE, linewidth=1.7, zorder=3,
             label='driven' if reference else None)
    if reference:
        ax1.legend(frameon=False, labelcolor=MUT, fontsize=9, loc='upper right')
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
    ref = next((sg.get('reference_cm') for sg in segments
                if sg.get('kind') == 'spline'), None)
    closure = chart(tour.name, frames, segments, wall, out, sub, reference=ref)
    print(f'\nclosure {closure:.1f} mm' if closure is not None else '\nno chart')
    print(f'chart {out}\ndata  {data}')
    if a.open:
        subprocess.run(['open', out], check=False)


if __name__ == '__main__':
    main()
