"""Sprint 031 ticket 017 behavioural verification.

Before the fix, a `RUN:` fiber held motion ownership as `kJob`, the
block-motion path refused to take it, and `RUN:straight:8` returned a
normal receipt while the robot moved 0.02 cm.  After the fix the
dispatching fiber is allowed to re-take its own ownership, so the same
command should drive ~8 cm.

Camera-truthed: the wire's own odometry cannot detect this failure --
that is exactly what made the defect invisible.
"""
import math
import sys
import time

sys.path.insert(0, 'tests/playfield')
sys.path.insert(0, 'tools')
import turn_calibration as tc      # noqa: E402
import field_dance as fd           # noqa: E402
from field import _within_margin   # noqa: E402

HOST, PORT = '192.168.4.52', 46011
PASS_FLOOR = 5.0   # [cm] below this is the old, broken behaviour
NOMINAL = 8.0      # [cm] what RUN:straight:8 asks for


def fix(label):
    p = fd.pose(n=6)
    if p is None:
        raise SystemExit(f'ABORT: camera saw no tag {fd.TAG} at "{label}"')
    print(f'  {label:<7} ({p[0]:+7.2f}, {p[1]:+7.2f}) cm  heading {p[2]:+7.2f} deg')
    return p


def main():
    link = tc.Link(HOST, PORT)
    link.hello()
    print('STATUS before:', link.status())

    before = fix('before')
    if not _within_margin(before[0], before[1]):
        raise SystemExit(f'ABORT: start ({before[0]:.1f}, {before[1]:.1f}) is '
                         'inside the 12 cm margin -- reposition first.')

    t0 = time.time()
    reply = link.unseq('RUN:straight:8', r'^(DBG:|ok|err|ack)', wait=8.0)
    print(f'  RUN:straight:8 -> {reply!r}  ({time.time() - t0:.1f} s)')
    time.sleep(2.5)

    after = fix('after')
    dx, dy = after[0] - before[0], after[1] - before[1]
    travel = math.hypot(dx, dy)
    bearing = math.degrees(math.atan2(dy, dx))
    err = (bearing - before[2] + 180.0) % 360.0 - 180.0

    print(f'\n  travel  {travel:.2f} cm (commanded {NOMINAL:.1f})')
    print(f'  bearing {bearing:+.1f} deg vs heading {before[2]:+.1f} '
          f'-> off {err:+.1f} deg')
    print('STATUS after: ', link.status())
    print('ID:', link.unseq('ID', r'^id ', wait=2.0))
    link.close()

    if travel >= PASS_FLOOR:
        print(f'\nPASS: RUN:straight drove {travel:.2f} cm. '
              'The ticket 017 fix is live on the board.')
        return 0
    print(f'\nFAIL: RUN:straight drove only {travel:.2f} cm -- block motion '
          'is still being refused.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
