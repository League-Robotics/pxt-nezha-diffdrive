"""Measure the CURRENT velocity profile out of the compiled motion
engine -- no hardware. Reuses the repo's own host harness so what is
measured is the real serviceMove(), not a reimplementation.

Run from the repo root:  uv run python <this file>
"""
import ctypes, pathlib, sys, tempfile

REPO = pathlib.Path('/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive')
sys.path.insert(0, str(REPO / 'tests' / 'host'))

import test_motion_engine_deadline_boundary as B
from test_kernel_harness import compile_shared_lib


class _Factory:
    """Stand-in for pytest's tmp_path_factory."""
    def __init__(self, d): self._d = pathlib.Path(d)
    def mktemp(self, name, numbered=True):
        p = self._d / name
        p.mkdir(parents=True, exist_ok=True)
        return p


def capture(lib, distance_mm, cruise_mm_s, timeout_ms=60000, max_ticks=4000):
    """One moveX(), driven tick by tick. Returns per-tick
    (t_ms, mean_speed_mm_s, remaining_mm)."""
    with B.Engine(lib) as e:
        fdv = B._ready(e)
        cpm = e.counts_per_mm() if hasattr(e, 'counts_per_mm') else None
        e.move_x(distance_mm, 0.0, cruise_mm_s, timeout_ms)
        pos = {B.LEFT: 0.0, B.RIGHT: 0.0}
        duty = {B.LEFT: e.motor_last_staged_duty(B.LEFT),
                B.RIGHT: e.motor_last_staged_duty(B.RIGHT)}
        t_ms = 0.0
        rows = []
        for _ in range(max_ticks):
            for side in (B.LEFT, B.RIGHT):
                pos[side] += duty[side] * fdv * (B.TICK_MS / 1000.0)
            t_ms += B.TICK_MS
            us = int(t_ms * 1000.0)
            e.arm_motor_position_at(B.LEFT, pos[B.LEFT], us)
            e.arm_motor_position_at(B.RIGHT, pos[B.RIGHT], us)
            e.set_clock(us)
            e.step()
            active = e.service_move()
            duty[B.LEFT] = e.motor_last_staged_duty(B.LEFT)
            duty[B.RIGHT] = e.motor_last_staged_duty(B.RIGHT)
            # counts/s commanded this tick, both wheels
            vl = duty[B.LEFT] * fdv
            vr = duty[B.RIGHT] * fdv
            mean_counts_s = 0.5 * (vl + vr)
            mean_counts = 0.5 * (pos[B.LEFT] + pos[B.RIGHT])
            rows.append((t_ms, mean_counts_s, mean_counts))
            if not active:
                break
        return rows, cpm


def main():
    with tempfile.TemporaryDirectory() as td:
        libpath = compile_shared_lib(_Factory(td), sources=B._SHIM_SOURCES,
                                     out_name="libprofile_probe.so")
        lib = B._bind(ctypes.CDLL(str(libpath)))

        # counts/mm: engine default travelCalib 0.7878 -> 10/0.7878
        CPM = 10.0 / 0.7878

        print("CURRENT PROFILE, measured from the compiled engine")
        print("(1000 mm leg; speeds converted counts/s -> mm/s via cpm=%.2f)\n" % CPM)
        print(" cruise |  peak | accel_to_peak | decel: measured a  | brake window | ticks decel")
        print(" (mm/s) |(mm/s) |    (mm/s^2)   |     (mm/s^2)       |    (mm)      |")
        print("--------+-------+---------------+--------------------+--------------+------------")
        for cruise in (100, 200, 300, 400, 600):
            rows, _ = capture(lib, 1000.0, float(cruise))
            t = [r[0] for r in rows]
            v = [r[1] / CPM for r in rows]          # mm/s
            d = [r[2] / CPM for r in rows]          # mm travelled
            pk = max(v)
            i_pk = v.index(pk)
            accel = (pk - v[0]) / max((t[i_pk] - t[0]) / 1000.0, 1e-3)
            # decel phase: from last index at >=90% peak to the end
            last90 = max(i for i, s in enumerate(v) if s >= 0.9 * pk)
            dt = (t[-1] - t[last90]) / 1000.0
            dec = (v[last90] - v[-1]) / dt if dt > 0 else float('inf')
            window = d[-1] - d[last90]
            nticks = len(v) - 1 - last90
            print(f" {cruise:6d} | {pk:5.0f} | {accel:13.0f} | {dec:18.0f} | {window:12.1f} | {nticks:11d}")

        print("\nWhat the numbers say:")
        print("  * accel scales with cruise (it is time-based, not an acceleration)")
        print("  * the brake window stays ~fixed, so required decel grows as v^2")
        print("  * at high cruise the decel phase collapses to a couple of ticks")


if __name__ == '__main__':
    main()
