import json, sys

FIELDS = ['seq', 'now', 'flags', 'x', 'y', 'h', 'ox', 'oy', 'oh', 'vl', 'vr',
          'i2cf', 'cyc', 'posl', 'posr', 'dutl', 'dutr', 'lexc', 'wrng', 'cycovr']
IDX = {name: i for i, name in enumerate(FIELDS)}
DUTY_RAIL = 10000

def analyze(frames, vel_threshold=50, dut_jump_threshold=500):
    events = []
    for i in range(2, len(frames) - 1):
        prev2, prev, cur, nxt = frames[i-2], frames[i-1], frames[i], frames[i+1]
        for side, pos_key, dut_key, vel_key in (('L','posl','dutl','vl'), ('R','posr','dutr','vr')):
            pos_prev, pos_cur = prev[IDX[pos_key]], cur[IDX[pos_key]]
            dut_cur, dut_before = cur[IDX[dut_key]], prev[IDX[dut_key]]
            vel_prev2 = prev2[IDX[vel_key]]
            if pos_cur == pos_prev and abs(dut_before) > 200 and abs(vel_prev2) > vel_threshold:
                # candidate: was moving at prev2, duty already established, pos froze at cur
                i2cf_prev, i2cf_cur = prev[IDX['i2cf']], cur[IDX['i2cf']]
                dut_next = nxt[IDX[dut_key]]
                jump_at = dut_cur - dut_before
                jump_next = dut_next - dut_before
                events.append(dict(
                    frame_index=i, side=side, pos=pos_cur,
                    vel_prev2=vel_prev2, vel_at=cur[IDX[vel_key]],
                    dut_before=dut_before, dut_at=dut_cur, dut_next=dut_next,
                    jump_at=jump_at, jump_next=jump_next,
                    i2cf_prev=i2cf_prev, i2cf_cur=i2cf_cur, i2cf_ticked=i2cf_cur>i2cf_prev,
                    stepped_toward_rail=(abs(jump_at) > dut_jump_threshold or abs(jump_next) > dut_jump_threshold),
                ))
    return events

if __name__ == '__main__':
    path = sys.argv[1]
    d = json.load(open(path))
    frames = d['frames']
    print(f"{len(frames)} frames loaded from {path}")
    events = analyze(frames)
    print(f"candidate frozen-while-moving events: {len(events)}")
    for e in events:
        print(f"  frame {e['frame_index']} side {e['side']}: pos={e['pos']} "
              f"vel_prev2={e['vel_prev2']} vel_at={e['vel_at']} "
              f"dut_before={e['dut_before']} dut_at={e['dut_at']} dut_next={e['dut_next']} "
              f"jump_at={e['jump_at']} jump_next={e['jump_next']} "
              f"i2cf {e['i2cf_prev']}->{e['i2cf_cur']} ticked={e['i2cf_ticked']} "
              f"stepped_toward_rail={e['stepped_toward_rail']}")
    n_ticked = sum(1 for e in events if e['i2cf_ticked'])
    n_step = sum(1 for e in events if e['stepped_toward_rail'])
    print(f"\nsummary: {len(events)} events, {n_ticked} with i2cf tick, {n_step} with duty step > threshold")
