#!/usr/bin/env python3
"""Run tours from the start dot, camera-scored, and chart each one.

For every run: reposition onto the NE orange dot facing west (verified
by the overhead camera, not assumed), start the tour, record telemetry
and camera continuously, then chart and score it.

Scoring is done by the CAMERA throughout. The robot's own sensors are
recorded alongside for comparison, but a tour that navigates by the
OTOS cannot be graded by the OTOS -- it would be marking its own
homework.

Wheel speeds ride the v6 telemetry frame's own vl/vr columns (the
kernel's own per-tick measurement, via tools/tlm.py) rather than being
polled: a request/reply round-trip inside a move over the wireless link
is measured to collapse a 197.5 mm leg to 0.3 mm.

  python3 tools/tour_practice.py [--tours robot world] [--runs 2]
"""
import argparse
import csv
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from robotlink import open_link
from reposition import Repositioner
from camproc import Cam
from field import ORDER, PathRefused, closure, score_corners
import tlm

START = (50.0, 30.0, 180.0)

TITLES = {'robot': 'Tour A — robot-relative (encoder only)',
          'world': 'Tour B — world goToWorld (OTOS-guided)',
          'wheels': 'Tour A+B — wheels (open loop)'}


def record_tour(link, cam, name, timeout=120):
    """Subscribe telemetry (aborting before the tour is triggered if the
    instrument is dead -- SUC-001), trigger the tour, and record until
    it ends.

    Returns (t0, pose, fixes, ended, stream): `stream` is the
    tools/tlm.py TlmStream the caller passes on to write_tlm_csv() for
    this run's own <stem>_tlm.csv/.meta.json -- already primed with at
    least one frame by require_stream(), so write_tlm_csv() cannot raise
    EmptyCaptureError against it.
    """
    stream = tlm.require_stream(link, timeout=3.0)
    t0 = time.time()
    link.send(f'RUN:tour:{name}')
    pose, fixes = [], []
    started = False
    end = time.time() + timeout
    while time.time() < end:
        for s in link.lines(1.0):
            if s.startswith('DBG:tour='):
                started = True
                t0 = time.time()
            elif not started:
                continue
            elif s.startswith('OCAL:c'):
                fixes.append(s)
            elif s.startswith('TOUR:end'):
                return t0, pose, fixes, True, stream
            else:
                row = stream.feed(s)
                if row is not None:
                    # The decoded frame IS the pose row, kept in the
                    # wire's own units for tlm.write_pose_csv(); it
                    # carries row['now'], the DEVICE timestamp [ms],
                    # which is what any dt must be taken from -- host
                    # arrival jitters badly over the wireless link and
                    # fabricates speed spikes.
                    pose.append(dict(row, t_host=time.time()))
        if started and time.time() - t0 > timeout:
            break
    return t0, pose, fixes, started, stream


def score(camrows):
    """Closest approach to each dot, in visit order, plus closure.

    Corner scoring itself lives in tools/field.py (score_corners()) --
    the same gap-aware algorithm every tour/ground-truth tool now
    calls, so this console report and practice_chart.py's chart (drawn
    from the same recorded run, in a separate subprocess) cannot
    disagree about which corners were actually observed.
    """
    if not camrows:
        return None
    res = score_corners(camrows)
    res['closure'], res['end_heading_err'] = closure(camrows, START[2])
    return res


def write_csv(path, header, rows):
    with open(path, 'w') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def chart(name, run, pose, camrows, sc, path, stem):
    """Chart in a subprocess: the system matplotlib is broken here, so
    plotting runs under uv while this process keeps pyserial.

    `pose` rows are decoded telemetry frames, written through
    tlm.write_pose_csv() -- the one pose-CSV schema (sprint 034 ticket
    004), in the wire's own units, with the optional `vl_mms,vr_mms`
    pair appended because practice_chart.py plots the frame's own wheel
    speeds. This tool used to write its own cm/degree header, which
    tour_chart.py would then read as wire units.
    """
    write_csv(stem + '_cam.csv', ['t', 'x_cm', 'y_cm', 'yaw_deg'],
              [[round(c[0], 3), round(c[1], 2), round(c[2], 2),
                round(c[3], 2)] for c in camrows])
    tlm.write_pose_csv(pose, stem + '_pose.csv', wheels=True)
    subprocess.run(['uv', 'run', '--with', 'numpy', '--with', 'matplotlib',
                    'python3',
                    os.path.dirname(os.path.abspath(__file__))
                    + '/practice_chart.py',
                    name, str(run), stem + '_cam.csv', stem + '_pose.csv',
                    path], check=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help="drive the robot over its WiFi TCP server instead of the "
             "radio relay (the default carrier since 2026-09-02)")
    ap.add_argument('--robot', default='vevov',
        help="board name -- resolves the zavaz relay's channel/group "
             "(field_calibration.json's override, else derived from the "
             "name) when driving over --radio; ignored for --wifi")
    ap.add_argument('--tours', nargs='+', default=['robot', 'world'])
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--outdir', default='.tmp/practice')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    cam = Cam()
    if cam.err or cam.latest is None:
        raise SystemExit(f'camera not usable: {cam.err or "no tag"}')
    link = open_link(radio=not a.wifi, wifi=a.wifi, robot=a.robot)
    rep = Repositioner(link, cam)

    results = []
    for run in range(1, a.runs + 1):
        for name in a.tours:
            print(f'\n=== {name} tour, run {run} ===')
            if name == 'world':
                # No repositioning: seed the TRUE pose from the camera
                # and let the robot drive to the first dot from
                # wherever it happens to be. That is the whole point of
                # a world-frame tour.
                p = rep.fix()
                if p is None:
                    print('  camera lost the robot; skipping')
                    continue
                link.send(f'RUN:seedxy:{p[0]:.1f}:{p[1]:.1f}:{p[2]:.1f}')
                for s2 in link.lines(6):
                    if s2.startswith('OCAL:seeded'):
                        break
                print(f'  seeded at ({p[0]:.1f}, {p[1]:.1f}) '
                      f'{p[2]:.1f} deg -- starting from here')
            else:
                # The robot-relative tour has no world frame, so it must
                # physically start on the dot facing west.
                print('  repositioning to the NE dot:')
                # Repositioner.go() pre-flights the leg against the
                # playfield margin and REFUSES rather than clamping --
                # print it and skip the run, never drive anyway.
                try:
                    start = rep.go(*START)
                except PathRefused as e:
                    print(f'  {e}')
                    continue
                if start is None:
                    print('  camera lost the robot; skipping')
                    continue
            time.sleep(1.0)
            # --- fail loud: a dead instrument must not cost a run
            # (SUC-001), checked by record_tour()'s own require_stream()
            # call before it sends RUN:tour: ---
            try:
                t0, pose, fixes, ok, stream = record_tour(link, cam, name)
            except tlm.DeadTelemetryError as e:
                print(f'  {e}')
                continue
            camrows = cam.since(t0)
            if not ok or not camrows:
                print(f'  tour did not report an end ({len(pose)} tlm, '
                      f'{len(camrows)} cam) -- skipping')
                continue
            sc = score(camrows)
            stem = f'{a.outdir}/{name}-run{run}'
            png = stem + '.png'
            chart(name, run, pose, camrows, sc, png, stem)
            # require_stream() inside record_tour() already guaranteed
            # `stream` has at least one frame, so this cannot raise
            # EmptyCaptureError here.
            meta = tlm.write_tlm_csv(stream, stem + '_tlm.csv')
            results.append((name, run, sc))
            print('  corners: ' + '  '.join(
                (f'{t} {sc[t]:.1f}cm' if sc[t] is not None
                 else f'{t} unobserved') for t in ORDER))
            print(f'  closure {sc["closure"]:.1f} cm, end heading '
                  f'{sc["end_heading_err"]:+.1f} deg, '
                  f'{len(pose)} tlm / {len(camrows)} cam samples')
            print(f'  telemetry: {meta["frames"]} frames, '
                  f'{meta["dropped"]} dropped ({meta["loss_pct"]:.1f}% loss)')
            print(f'  -> {png}')
            subprocess.run(['open', png])

    link.close()
    cam.close()

    if results:
        print('\n===== summary (camera-scored) =====')
        print(f"{'tour':8} {'run':>3} " + ' '.join(f'{t:>7}' for t in ORDER)
              + f" {'closure':>8} {'endhdg':>7}")
        def fmt7(v):
            return f'{v:7.1f}' if v is not None else f'{"n/a":>7}'

        for name, run, sc in results:
            print(f'{name:8} {run:>3} '
                  + ' '.join(fmt7(sc[t]) for t in ORDER)
                  + f' {sc["closure"]:8.1f} {sc["end_heading_err"]:+7.1f}')


if __name__ == '__main__':
    main()
