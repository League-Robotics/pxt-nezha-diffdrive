---
title: "Stack-canary flash + pyOCD scan (sprint 031 ticket 014) was never run; deferred"
status: pending
created: 2026-09-05
---

# Stack-canary scan deferred from sprint 031

Sprint 031 ticket 014 (flash the `--fault-spin` canary build, run a
tour, scan the stack with pyOCD, reflash the plain build) was never
executed. The build variant exists and is tested
(`tools/make_deploy.py --fault-spin`, `tests/tools/test_make_deploy_fault_spin.py`,
19 tests, sprint 031 ticket 013) -- only the hardware half is missing.

It was deferred on 2026-09-05 because it is instrumentation for a
stack-overflow hypothesis, not a release blocker, and the session's
hardware time went to the drivetrain findings in
`docs/sprint-031-postmortem.md`. Nothing in the student release
depends on it.

## To run it

1. Board on the farm (or zilch with pyOCD): `mbdeploy deploy tovez
   --remote` with the `--fault-spin` hex.
2. One square tour.
3. pyOCD read of the canary region; expect the pattern intact.
4. Reflash the plain build and confirm `ID` -- note both builds may
   report the SAME version string (`bump-the-version-before-a-behaviour-flash`);
   verify by the `-faultspin` profile suffix `make_deploy.py` injects.

Original ticket text preserved at
`clasi/sprints/031-drivetrain-tuning-and-gate-acceptance-on-tovez/tickets/`.
