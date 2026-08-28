"""Run D: same WHEELS_V step with pid_i_max halved (30 mm/s), restore after."""
import json, sys, time
from capture import Session
from exp import run_leg

s = Session()
banner = s.hello()
print(f'relay={s.relay} robot={banner}', flush=True)
assert banner and 'tovez' in banner

ack, _ = s.seq('SET pid_i_max 383')     # 30 mm/s x 12.76 counts/mm
print('SET pid_i_max 383 ->', ack, flush=True)
run = run_leg(s, 'D-wheelsv-imax30', [
    ('WHEELS_V 0 0 800', 1.0),
    ('WHEELS_V 200 200 4000', 3.8),
    ('WHEELS_V 0 0 1500', 1.5),
])
ack, _ = s.seq('SET pid_i_max 765.6')   # restore baked value
print('SET pid_i_max 765.6 (restore) ->', ack, flush=True)
m = s.mark(); s.seq('GET pid_i_max', wait=1.5); time.sleep(0.4)
for _, ln in s.since(m):
    if 'get pid_i_max' in ln: print('restored:', ln.strip(), flush=True)
s.close()
json.dump(run, open(sys.argv[1], 'w'))
print('wrote', sys.argv[1], flush=True)
