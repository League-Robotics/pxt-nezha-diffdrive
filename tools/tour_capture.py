#!/usr/bin/env python3
"""Square Tour capture — the standard telemetry recorder.

Sends RUN:<n> over the robot's USB serial and records the v6 thdr/t
telemetry stream via tools/tlm.py (device-timestamped pose, in wire
units: mm/cdeg), writing the pose CSV tools/tour_chart.py plots plus
tlm.py's own <out-prefix>_tlm.csv/.meta.json capture-quality sidecar.

The wheel-speed poll below (DIAG, ~8 Hz, wired only) targets a verb
retired in the v6 cutover (sprint 003) -- it is a documented, currently
inert no-op on this firmware (`_vel.csv` will be empty), kept rather
than removed because fixing/retiring it is outside this ticket's scope
(sprint 005 ticket 002; see the ticket's own report for the finding).
The v6 telemetry frame already carries `vl`/`vr` per frame -- once DIAG
is formally retired here too, that column supersedes this poll entirely.

Usage:
  python3 tools/tour_capture.py PORT [--run 1] [--timeout 60]
      [--out-prefix .tmp/tour]
"""
import argparse
import csv
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link
import tlm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default=None,
                    help='serial port; omit with --radio for zavaz')
    ap.add_argument('--radio', action='store_true',
                    help='capture over the zavaz relay (robot on the '
                         'playfield). The bench stand holds the wheels off '
                         'the ground, so any OTOS column is meaningless '
                         'there.')
    ap.add_argument('--run', type=int, default=1)
    ap.add_argument('--timeout', type=float, default=60.0)
    ap.add_argument('--out-prefix', default='.tmp/tour')
    a = ap.parse_args()

    link = open_link(a.port, radio=a.radio)
    p = link.p

    # --- fail loud: a dead instrument must not cost a run (SUC-001) ---
    try:
        stream = tlm.require_stream(link, timeout=3.0)
    except tlm.DeadTelemetryError as e:
        raise SystemExit(str(e))

    pose, vel = [], []
    t0 = time.time()
    # The tour marks itself in the stream; resend only if that receipt
    # never arrives (a duplicate RUN re-runs the whole tour).
    link.send_until(f'RUN:{a.run}', 'TOUR:', tries=3, wait=6.0)
    last_diag = 0.0
    egl = gap = None
    last_pose_change = time.time()
    last_pose_vals = None
    end = time.time() + a.timeout
    while time.time() < end:
        if pose and time.time() - last_pose_change > 4.0 \
                and time.time() - t0 > 6.0:
            break  # motion over (fallback for a missed GAP line)
        now = time.time() - t0
        # NEVER poll during a move over the wireless link: a
        # request/reply round-trip inside a move is actively dangerous
        # there -- measured upstream, polling telemetry mid-move cut a
        # leg from 197.5 mm to 0.3 mm. The v6 thdr/t stream flows
        # unprompted once subscribed (require_stream() above already
        # sent TLM POSE), so the pose track survives; wheel speeds via
        # DIAG are simply unavailable untethered (and, on this firmware,
        # unavailable wired too -- see the module docstring). The
        # per-corner OCAL fixes are currently UNRELIABLE for scoring:
        # they read a stale cached pose, not a live measurement (see
        # clasi/issues/tour-corner-fixes-are-stale-cache.md) -- do not
        # trust a tour closure number derived from them until that is
        # fixed.
        if not a.radio and now - last_diag > 0.12:
            link.send('DIAG')
            last_diag = now
        line = p.readline()
        if not line:
            continue
        s = line.decode('ascii', errors='replace').strip()
        if s.startswith('< '):
            s = s[2:]          # relay control-plane prefix
        row = stream.feed(s)
        if row is not None:
            # x/y/ox/oy already mm, h/oh already cdeg on the wire -- no
            # scale factor of this tool's own (tlm.py owns the one place
            # any wire-to-engineering-unit conversion happens).
            pose.append((round(now, 3), row['now'], row['x'], row['y'],
                         row['h'], row['ox'], row['oy'], row['oh']))
            vals = (row['x'], row['y'], row['h'])
            if vals != last_pose_vals:
                last_pose_vals = vals
                last_pose_change = time.time()
        elif s.startswith('DIAG:'):
            i = s.find('vel=')
            if i >= 0:
                try:
                    vl, vr = s[i + 4:].split(',')[0].split('/')
                    vel.append((round(now, 3), int(vl), int(vr)))
                except ValueError:
                    pass
            j = s.find('egl=')
            if j >= 0:
                egl = s[j:].split(',')[0]
        elif s.startswith('GAP:'):
            gap = s
            if time.time() < end - 3:
                end = time.time() + 1.5   # test done; short tail
    link.close()

    with open(a.out_prefix + '_pose.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(['t_host', 't_dev_ms', 'x_mm', 'y_mm', 'h_cdeg',
                    'ox_mm', 'oy_mm', 'oh_cdeg'])
        w.writerows(pose)
    with open(a.out_prefix + '_vel.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(['t_host', 'vel_l_counts', 'vel_r_counts'])
        w.writerows(vel)
    # tlm.py's own raw-wire-unit CSV + capture-quality sidecar --
    # require_stream() above guarantees `stream` already has at least
    # one frame, so this cannot raise EmptyCaptureError here.
    meta = tlm.write_tlm_csv(stream, a.out_prefix + '_tlm.csv')
    final = pose[-1] if pose else None
    print(f"captured {len(pose)} pose / {len(vel)} vel rows; "
          f"final {final}; {egl}; {gap}; "
          f"telemetry {meta['frames']} frames, {meta['dropped']} dropped "
          f"({meta['loss_pct']:.1f}% loss)")


if __name__ == '__main__':
    main()
