"""Run a plan of MOVE_X straight legs on tovez over the radio relay pool,
recording TLM FULL frames + an event log, for end-of-leg analysis.

    python3 legs.py plan.json out.json

Plan: {"phases": [{"name": ..., "set": {field: value, ...},
                   "legs": [[dist_mm, cruise_mmps, timeout_ms?], ...]}, ...]}

Every phase's SETs are ack-verified and read back with GET; the baseline
config (bare GET dump at connect) is restored at the end and read back
again. Completion of each leg is detected from telemetry (5 live frames
at rest, then a 0.7 s grace re-check so the engine's late finish is not
superseded -- measured need: captures/tovez-square-20260828/), never a
fixed sleep. Bench or floor is NOT assumed: the OTOS ox/oy/oh deltas over
the warm-up are printed so the surface is read from the data.
"""
import json
import sys
import time

from session_radio import Session, parse_frames

FIELDS = ('max_duty full_duty_velocity pid_kp pid_ki pid_i_max accel_kaff '
          'pid_max twist_hold_gain speed_floor pos_err_max crawl_pulse').split()


def latest(s, n=30):
    return parse_frames(s.since(0)[-n:])


def get_all(s):
    """Per-field GETs (each ack-verified and retried): the bare-GET dump
    loses lines over the radio (measured in baseline.log, 2026-08-29)."""
    out = {}
    for f in FIELDS:
        v = s.get(f)
        if v is not None:
            out[f] = v
    return out


def set_and_verify(s, field, value):
    ack, tries = s.seq(f'SET {field} {value}')
    if ack is None:
        raise RuntimeError(f'SET {field} never acked')
    rb = s.get(field)
    print(f'  SET {field} {value} -> ack (attempts={tries+1}); GET -> {rb}',
          flush=True)
    if rb is None or abs(rb - value) > max(1e-3, 1e-3 * abs(value)):
        raise RuntimeError(f'SET {field} {value} read back {rb}')
    return rb


def wait_done(s, t_ack, min_dur, wall=20.0):
    """Block until the current move looks finished. Returns ('still'|'frozen')."""
    last_cyc, last_cyc_t = None, time.time()
    deadline = time.time() + wall
    while time.time() < deadline:
        time.sleep(0.15)
        frames = latest(s, 40)
        if not frames:
            continue
        r = frames[-1]
        if last_cyc is None or r['cyc'] != last_cyc:
            last_cyc, last_cyc_t = r['cyc'], time.time()
        if time.time() - s.t0 - t_ack < min_dur:
            continue
        quiet, pc = 0, None
        for fr in frames[-10:]:
            lv = pc is None or fr['cyc'] > pc
            pc = fr['cyc']
            if lv and abs(fr['vl']) <= 20 and abs(fr['vr']) <= 20:
                quiet += 1
            elif lv:
                quiet = 0
        if quiet >= 5:
            time.sleep(0.7)
            tail = latest(s, 12)[-6:]
            if any(abs(r['vl']) > 20 or abs(r['vr']) > 20 for r in tail):
                continue
            return 'still'
        if time.time() - last_cyc_t > 0.8:
            return 'frozen'
    raise RuntimeError('move did not finish inside the wall timeout')


def run_leg(s, verb, min_dur, events, tag):
    t_send = time.time() - s.t0
    ack, tries = s.seq(verb, tries=8, wait=1.5)
    t_ack = time.time() - s.t0
    if ack is None:
        raise RuntimeError(f'never acked: {verb}')
    how = wait_done(s, t_ack, min_dur)
    ev = {'verb': verb, 't_send': t_send, 't_ack': t_ack, 'done_via': how,
          'attempts': tries + 1, **tag}
    events.append(ev)
    print(f'  {verb:28s} ack={ack.strip():14s} tries={tries+1} done={how}',
          flush=True)
    time.sleep(0.6)
    return ev


def main():
    plan = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    s = Session()
    banner = s.hello()
    print(f'relay={s.relay} robot={banner}', flush=True)
    assert banner and 'tovez' in banner, 'HELLO did not identify tovez'

    baseline = get_all(s)
    print('baseline config:', json.dumps(baseline), flush=True)

    ack, tries = s.seq('TLM FULL')
    print(f'TLM FULL -> {ack} (attempts={tries+1})', flush=True)
    time.sleep(0.8)
    start_mark = s.mark()
    events = []

    # Warm-up: net-zero, both motors broken away recently.
    f0 = latest(s)[-1]
    for verb in ('MOVE_X 40 0 150 6000', 'MOVE_X -40 0 150 6000') * 2:
        run_leg(s, verb, 0.5, events, {'phase': 'warmup'})
    f1 = latest(s)[-1]
    print(f'warm-up OTOS delta: dox={f1["ox"]-f0["ox"]} doy={f1["oy"]-f0["oy"]} '
          f'doh={f1["oh"]-f0["oh"]}  (encoder pose dx={f1["x"]-f0["x"]} '
          f'dy={f1["y"]-f0["y"]}) -- ~0 means wheels-up bench', flush=True)

    try:
        for ph in plan['phases']:
            print(f'== phase {ph["name"]} set={ph.get("set", {})}', flush=True)
            applied = {}
            for k, v in ph.get('set', {}).items():
                applied[k] = set_and_verify(s, k, v)
            for leg in ph['legs']:
                d, cruise = leg[0], leg[1]
                tmo = leg[2] if len(leg) > 2 else 10000
                verb = f'MOVE_X {d} 0 {cruise} {tmo}'
                min_dur = 0.7 * abs(d) / cruise + 0.3
                run_leg(s, verb, min_dur, events,
                        {'phase': ph['name'], 'dist': d, 'cruise': cruise,
                         'timeout': tmo, 'set': applied})
            # restore this phase's fields before the next one
            for k in ph.get('set', {}):
                set_and_verify(s, k, baseline[k])
    finally:
        restored = get_all(s)
        diffs = {k: (baseline.get(k), restored.get(k)) for k in FIELDS
                 if baseline.get(k) != restored.get(k)}
        print('restore check, differing fields:', diffs or 'none', flush=True)
        time.sleep(1.0)
        end_mark = s.mark()
        s.seq('TLM OFF')
        relay = s.relay
        frames = parse_frames(s.since(start_mark)[:end_mark - start_mark])
        s.close()
        json.dump({'robot': 'tovez', 'relay': relay, 'plan': plan,
                   'baseline_config': baseline, 'restored_config': restored,
                   'events': events, 'frames': frames}, open(out, 'w'))
        print(f'frames={len(frames)} events={len(events)} wrote {out}',
              flush=True)


if __name__ == '__main__':
    main()
