#!/usr/bin/env python3
"""Turn accuracy vs speed: sweep angle against yaw rate, camera-scored.

Each cell commands one pivot and records what the overhead camera
actually measured against what was asked. The robot's own view
(encoder differential, tick count, peak duty) rides along, so a
disagreement between camera and encoders is visible rather than
assumed -- and peak duty flags the point where the commanded rate
exceeds what the drivetrain can deliver.

Alternates sign each repeat so a systematic direction bias shows up as
a split rather than hiding in the mean.

Robot must be ON THE FLOOR and in camera view, with a calibrated
daemon. Run under the system python (it has pyserial); the camera runs
as its own process under the AprilTags venv.

  python3 tools/turn_sweep.py [--angles 45 90 180] [--rates 15 45 90]
                              [--reps 2] [--csv out.csv]
"""
import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from camproc import Cam
from field import wrap


def _yaw_mark(cam):
    """(total unwrapped yaw turned so far, sample count, err) --
    computed fresh from `cam`'s own recorded samples each call,
    mirroring the old CamStream.mark()'s (total, n, err) shape so
    one_turn() below needs no other change. `cam` is a
    tools/camproc.py Cam.

    Unwrapping this way is what makes turns beyond 180 deg (and
    multi-turn 360s) measurable at all: a before/after pair cannot
    tell +180 from -180, and cannot see a full revolution whatsoever.
    """
    with cam.lock:
        samples = list(cam.samples)
        err = cam.err
    total, prev = 0.0, None
    for _, _, _, yaw in samples:
        if prev is not None:
            total += wrap(yaw - prev)
        prev = yaw
    return total, len(samples), err


def one_turn(link, cam, deg, rate, settle):
    """Command one pivot; return a result row or None if unmeasurable."""
    link.send(f'RUN:turnrate:{int(rate)}')
    time.sleep(0.4)
    t0, n0, err = _yaw_mark(cam)
    if err:
        return None, err

    link.send(f'RUN:pivot:{int(deg)}')
    trn = None
    # A slow big turn takes a while; allow generously, plus the taper.
    budget = abs(deg) / max(rate, 1) + 15.0
    for s in link.lines(budget, until='TRN:'):
        if s.startswith('TRN:'):
            trn = s
    time.sleep(settle)
    t1, n1, err = _yaw_mark(cam)
    if err:
        return None, err
    if n1 - n0 < 8:
        return None, f'only {n1-n0} camera samples'

    camdeg = t1 - t0
    row = {'commanded': deg, 'rate': rate, 'camera': round(camdeg, 1),
           'error': round(camdeg - deg, 1)}
    if trn:
        f = trn.split(':')
        if len(f) == 8:
            try:
                row.update(enc_counts=int(f[3]), ticks=int(f[4]),
                           ms=int(f[5]), peak_duty=int(f[6]),
                           wrongway=int(f[7]))
            except ValueError:
                pass
    if row.get('ms'):
        row['actual_rate'] = round(abs(camdeg) / (row['ms'] / 1000.0), 1)
    return row, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--angles', type=int, nargs='+',
                    default=[45, 90, 180, 360])
    ap.add_argument('--rates', type=int, nargs='+',
                    default=[15, 30, 45, 90, 180, 360])
    ap.add_argument('--reps', type=int, default=2)
    ap.add_argument('--settle', type=float, default=1.5)
    ap.add_argument('--csv', default=None)
    a = ap.parse_args()

    cam = Cam()
    if cam.err or not cam.samples:
        raise SystemExit(f'camera not usable: {cam.err or "no tag seen"}')
    link = open_link(radio=not a.wifi, wifi=a.wifi)

    print(f"{'cmd':>5} {'rate':>5} {'camera':>8} {'error':>7} {'act rate':>9}"
          f" {'ticks':>6} {'duty':>6}  note")
    rows = []
    for rate in a.rates:
        for angle in a.angles:
            for rep in range(a.reps):
                # Alternate sign per repeat: a direction bias then shows
                # as a split instead of averaging itself away.
                deg = angle if rep % 2 == 0 else -angle
                row, err = one_turn(link, cam, deg, rate, a.settle)
                if err:
                    print(f"{deg:5d} {rate:5d}  -- {err}")
                    if 'ERR' in str(err):
                        link.close(); cam.close()
                        raise SystemExit('camera daemon died')
                    continue
                rows.append(row)
                note = ''
                if row.get('peak_duty', 0) >= 9900:
                    note = 'SATURATED'
                if row.get('wrongway'):
                    note += ' wrong-way-abort'
                print(f"{row['commanded']:5d} {row['rate']:5d}"
                      f" {row['camera']:8.1f} {row['error']:7.1f}"
                      f" {row.get('actual_rate', 0):9.1f}"
                      f" {row.get('ticks', 0):6d}"
                      f" {row.get('peak_duty', 0)/100:6.0f}  {note}")

    link.close()
    cam.close()

    if a.csv and rows:
        keys = ['commanded', 'rate', 'camera', 'error', 'actual_rate',
                'enc_counts', 'ticks', 'ms', 'peak_duty', 'wrongway']
        with open(a.csv, 'w') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in keys})
        print(f'\nwrote {len(rows)} rows -> {a.csv}')

    if rows:
        print('\nmean |error| by commanded rate:')
        for rate in a.rates:
            sel = [abs(r['error']) for r in rows if r['rate'] == rate]
            if sel:
                sat = sum(1 for r in rows if r['rate'] == rate
                          and r.get('peak_duty', 0) >= 9900)
                print(f"  {rate:4d} deg/s: {sum(sel)/len(sel):5.1f} deg "
                      f"(worst {max(sel):5.1f}, n={len(sel)}"
                      f"{', ' + str(sat) + ' saturated' if sat else ''})")


if __name__ == '__main__':
    main()
