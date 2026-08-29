"""A/B/C: overshoot vs pid_kp damping vs MOVE_X's shaped reference.

Each variant drives one 200 mm/s leg on the bench and captures TLM FULL.
SET changes are runtime-only; pid_kp is restored to 0 afterwards and a
power cycle clears everything anyway.
"""
import json
import sys
import time

from capture import Session, parse_frames


def run_leg(s, label, cmds, settle=1.2):
    """cmds: list of (verb, wait_after_s). Returns frames + event log."""
    ack, tries = s.seq('TLM FULL')
    print(f'{label}: TLM FULL -> {ack} (attempts={tries+1})', flush=True)
    time.sleep(0.8)
    start = s.mark()
    events = []
    for verb, wait in cmds:
        t_send = time.time() - s.t0
        ack, tries = s.seq(verb)
        print(f'{label}: {verb} -> {ack} (attempts={tries+1})', flush=True)
        if ack is None:
            raise RuntimeError(f'{label}: {verb} never acked')
        events.append({'verb': verb, 't_send': t_send})
        time.sleep(wait)
    time.sleep(settle)
    end = s.mark()
    s.seq('TLM OFF')
    time.sleep(0.3)
    return {'label': label, 'events': events,
            'frames': parse_frames(s.since(start)[:end - start])}


def main():
    s = Session()
    banner = s.hello()
    print(f'relay={s.relay} robot={banner}', flush=True)
    assert banner and 'tovez' in banner

    # record the live config this experiment runs under
    cfg = {}
    for fld in ('pid_kp', 'pid_ki', 'pid_i_max', 'pos_err_max',
                'full_duty_velocity', 'max_duty'):
        for _ in range(3):
            m = s.mark()
            got, _ = s.seq(f'GET {fld}', wait=1.5)
            time.sleep(0.4)
            val = None
            for _, ln in s.since(m):
                if f'get {fld} ' in ln:
                    val = float(ln.split()[-1])
            if val is not None:
                cfg[fld] = val
                break
    print('live config:', cfg, flush=True)

    runs = []

    # A: baseline step (kp=0) -- fresh copy so all three share a session
    runs.append(run_leg(s, 'A-wheelsv-kp0', [
        ('WHEELS_V 0 0 800', 1.0),
        ('WHEELS_V 200 200 4000', 3.8),
        ('WHEELS_V 0 0 1500', 1.5),
    ]))

    # B: same step with kp damping
    ack, _ = s.seq('SET pid_kp 0.5')
    print('SET pid_kp 0.5 ->', ack, flush=True)
    runs.append(run_leg(s, 'B-wheelsv-kp0.5', [
        ('WHEELS_V 0 0 800', 1.0),
        ('WHEELS_V 200 200 4000', 3.8),
        ('WHEELS_V 0 0 1500', 1.5),
    ]))
    ack, _ = s.seq('SET pid_kp 0')
    print('SET pid_kp 0 (restore) ->', ack, flush=True)

    # C: shaped reference -- MOVE_X 800 mm @ 200 mm/s cruise (ramp+taper)
    runs.append(run_leg(s, 'C-movex-800mm', [
        ('MOVE_X 800 0 200 8000', 6.5),
    ], settle=1.5))

    # verify restore
    m = s.mark()
    s.seq('GET pid_kp', wait=1.5)
    time.sleep(0.4)
    for _, ln in s.since(m):
        if 'get pid_kp' in ln:
            print('restored:', ln.strip(), flush=True)
    s.close()

    out = sys.argv[1] if len(sys.argv) > 1 else 'exp.json'
    with open(out, 'w') as fh:
        json.dump({'config': cfg, 'runs': runs}, fh)
    print('wrote', out, flush=True)


if __name__ == '__main__':
    main()
