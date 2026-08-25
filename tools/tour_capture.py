#!/usr/bin/env python3
"""Square Tour capture — the standard telemetry recorder.

Starts a tour and records the v6 thdr/t telemetry stream via
tools/tlm.py (device-timestamped pose, in wire units: mm/cdeg),
writing the pose and wheel-speed CSVs tools/tour_chart.py plots plus
tlm.py's own <out-prefix>_tlm.csv/.meta.json capture-quality sidecar.

**Named RUN verbs, never numeric.** `test.ts` dispatches `onRun()` on
a STRING key, so `RUN:1` matches no handler and is a silent no-op: the
tool runs to completion, prints numbers, and the robot never moved.
Sprint 005 ticket 006 retargeted five tools off that dead vocabulary
(see tests/tools/test_run_verbs.py) but did not reach this one, which
was still sending `RUN:<n>`. Tours are `RUN:tour:<name>`.

**Wheel speeds come from the telemetry frame, not from DIAG.** DIAG
was retired in the v6 cutover, so polling it produced an empty
`_vel.csv`. The v6 frame already carries `vl`/`vr` every frame, in
mm/s, which is strictly better: no calibration constant, and it
survives the radio where mid-move polling is forbidden outright.

Usage:
  python3 tools/tour_capture.py [PORT] [--radio] [--tour world|robot|wheels]
      [--timeout 60] [--out-prefix .tmp/tour]
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
    ap.add_argument('--tour', default='world',
                    choices=['world', 'robot', 'wheels'],
                    help="named tour for RUN:tour:<name>. On the BENCH "
                         "STAND only 'wheels' is meaningful: the other two "
                         "close their loops on an IMU that never rotates "
                         "and an OTOS that never translates with the "
                         "wheels off the ground.")
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
    # Wait for DBG:tour=<name>, which the tour emits as it STARTS -- not
    # for `TOUR:`, whose only match is the TOUR:end line emitted ~28 s
    # later when the whole tour has finished. Waiting on the end marker
    # with tries=3/wait=6.0 guarantees two resends before the first run
    # is anywhere near done, and a repeat does NOT hit the firmware's
    # re-entry guard: MessageBus events queue and run one after another,
    # so each resend runs the whole tour again.
    cmd = f'RUN:tour:{a.tour}'
    seen = link.send_until(cmd, 'DBG:tour=', tries=3, wait=6.0)
    if not any(x.startswith('DBG:tour=') for x in seen):
        print(f'  WARNING: no DBG:tour= receipt for {cmd} -- the tour may '
              f'never have started. Recording anyway.')
    gap = None
    last_pose_change = time.time()
    last_pose_vals = None
    end = time.time() + a.timeout
    while time.time() < end:
        if pose and time.time() - last_pose_change > 4.0 \
                and time.time() - t0 > 6.0:
            break  # motion over (fallback for a missed GAP line)
        now = time.time() - t0
        # Nothing is POLLED inside the loop, deliberately. A
        # request/reply round-trip inside a move over the wireless link
        # is actively dangerous -- measured upstream, polling telemetry
        # mid-move cut a 197.5 mm leg to 0.3 mm. The v6 thdr/t stream
        # flows unprompted once subscribed (require_stream() above sent
        # TLM POSE), and it carries vl/vr, so both the pose track and
        # the wheel-speed track come free of any round trip.
        #
        # The per-corner OCAL fixes are currently UNRELIABLE for
        # scoring: they read a stale cached pose, not a live
        # measurement (clasi/issues/tour-corner-fixes-are-stale-cache
        # .md). Do not trust a tour closure number derived from them --
        # score against the overhead camera instead.
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
            w = tlm.wheels_mms(row)
            vel.append((round(now, 3), w['vl'], w['vr']))
            vals = (row['x'], row['y'], row['h'])
            if vals != last_pose_vals:
                last_pose_vals = vals
                last_pose_change = time.time()
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
        # mm/s straight off the wire -- NOT encoder counts. The
        # travelCalib that DIAG's old `vel=` needed must never be
        # applied to these; doing so is a ~12x error that plots
        # perfectly plausibly (a 20 cm/s leg reads as 1.6 cm/s).
        w.writerow(['t_host', 'vel_l_mmps', 'vel_r_mmps'])
        w.writerows(vel)
    # tlm.py's own raw-wire-unit CSV + capture-quality sidecar --
    # require_stream() above guarantees `stream` already has at least
    # one frame, so this cannot raise EmptyCaptureError here.
    meta = tlm.write_tlm_csv(stream, a.out_prefix + '_tlm.csv')
    final = pose[-1] if pose else None
    print(f"captured {len(pose)} pose / {len(vel)} vel rows; "
          f"final {final}; {gap}; "
          f"telemetry {meta['frames']} frames, {meta['dropped']} dropped "
          f"({meta['loss_pct']:.1f}% loss)")


if __name__ == '__main__':
    main()
