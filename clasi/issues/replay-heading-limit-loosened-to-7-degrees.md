---
status: pending
---

# Ticket 012 loosened the replay heading limit from 3.5 to 7.0 deg

`tests/host/test_pose_estimator_replay.py` replays vevov's 54 min / 100 m
drift capture through the host-built estimator and scores heading against
the camera. Before ticket 012 the second-half heading rms was 2.0 deg
(limit 3.5); after it, 5.6 deg, and the limit was raised to 7.0 to pass.
Eric (2026-10-29): 7 deg is too big for any situation we have.

On hardware the same firmware did 2.35 deg rms over tovez's 100 m run, so
either ticket 012 made vevov's case worse or the replay's reconstructed
gyro (synthesised between per-leg rows from encoder progress) stopped
matching what the estimator now trusts in motion. Find out which, then
put the limit back to 3.5 deg or lower. The module docstring still quotes
the pre-012 measurement.
