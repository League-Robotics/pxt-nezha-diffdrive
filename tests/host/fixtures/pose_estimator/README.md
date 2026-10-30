# pose_estimator fixtures

Byte-for-byte copies of captures from `captures/` (gitignored), read by
`tests/host/test_pose_estimator_replay.py`. Logged by `tests/dev/otos_drift.py`
and `tests/dev/otos_gyro.py`; one TLM row per leg (drift1) or per 20 s.

| file | original | board | date |
|---|---|---|---|
| drift1.jsonl | captures/vevov-otos-drift-20261028/drift1.jsonl | vevov | 2026-10-28, 100 m camera-truthed run, 54 min |
| gyro1.jsonl | captures/vevov-otos-drift-20261028/gyro1.jsonl | vevov | 2026-10-28 16:58, stationary; the robot was moved at row 59 |
| fleet-gopiv.jsonl | captures/otos-gyro-fleet-20261028/gopiv.jsonl | gopiv | 2026-10-28 18:24, fresh boot, 30 min still |
| fleet-vevov.jsonl | captures/otos-gyro-fleet-20261028/vevov.jsonl | vevov | same |
| fleet-tovez.jsonl | captures/otos-gyro-fleet-20261028/tovez.jsonl | tovez | same |
| fleet-zuvat.jsonl | captures/otos-gyro-fleet-20261028/zuvat.jsonl | zuvat | same |
