#!/usr/bin/env python3
"""Square Tour capture — the standard telemetry recorder.

Sends RUN:<n> over the robot's USB serial, records the TLM pose stream
(device-timestamped: TLM:t_ms:x:y:h) and wheel speeds (DIAG polled at
~8 Hz), and writes the two CSVs tools/tour_chart.py plots.

Usage:
  python3 tools/tour_capture.py PORT [--run 1] [--timeout 60]
      [--out-prefix .tmp/tour]
"""
import argparse
import csv
import time

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port')
    ap.add_argument('--run', type=int, default=1)
    ap.add_argument('--timeout', type=float, default=60.0)
    ap.add_argument('--out-prefix', default='.tmp/tour')
    a = ap.parse_args()

    p = serial.Serial(a.port, 115200, timeout=0.05)
    time.sleep(1.5)
    p.reset_input_buffer()

    pose, vel = [], []
    t0 = time.time()
    p.write(f'RUN:{a.run}\n'.encode())
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
        if now - last_diag > 0.12:
            p.write(b'DIAG\n')
            last_diag = now
        line = p.readline()
        if not line:
            continue
        s = line.decode('ascii', errors='replace').strip()
        if s.startswith('TLM:'):
            parts = s[4:].split(':')
            try:
                if len(parts) == 4:      # device-timestamped format
                    t_dev, x, y, h = (int(v) for v in parts)
                elif len(parts) == 3:    # legacy, host time only
                    t_dev = -1
                    x, y, h = (int(v) for v in parts)
                else:
                    continue
                pose.append((round(now, 3), t_dev, x, y, h))
                if (x, y, h) != last_pose_vals:
                    last_pose_vals = (x, y, h)
                    last_pose_change = time.time()
            except ValueError:
                pass
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
    p.close()

    with open(a.out_prefix + '_pose.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(['t_host', 't_dev_ms', 'x_mm', 'y_mm', 'h_cdeg'])
        w.writerows(pose)
    with open(a.out_prefix + '_vel.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(['t_host', 'vel_l_counts', 'vel_r_counts'])
        w.writerows(vel)
    final = pose[-1] if pose else None
    print(f"captured {len(pose)} pose / {len(vel)} vel rows; "
          f"final {final}; {egl}; {gap}")


if __name__ == '__main__':
    main()
