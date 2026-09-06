---
title: Bench acceptance of the sprint 034 consolidated link, camera and geofence (deferred
  from ticket 013)
status: done
created: 2026-09-06
---

# Bench acceptance of the sprint 034 consolidated tools

Sprint 034 (closed 2026-09-06) consolidated the bench tooling: one
sequencer in `tools/link.py`, one in-process `camlink.Cam`, one
`field.wrap()`, one `Repositioner`, one pose-CSV codec, the geofence
wired into every planner, and `_V6_VERBS` drift-tested against the
firmware's verb table. Every ticket was verified host-side with
injected fakes. Ticket 013 (optional, hardware, `completes_issue:
false`) named the three things the host suite cannot prove and its
host half landed (`tests/calibration/consolidation_acceptance.py`,
55 tests); the on-robot half was NOT run overnight -- no board was
assigned for that session and the ticket itself says not to run it
in the overnight batch.

## What would settle it

One scripted session by the team-lead on a stakeholder-assigned board:

```
curl -s "http://192.168.1.122/rpc/Switch.Set?id=0&on=true"     # lights
uv run python tests/calibration/calibrate.py acceptance <robot> --dry-run
uv run python tests/calibration/calibrate.py acceptance <robot> --dot NE
uv run python tools/wire_acceptance.py --wifi-tcp <robot>
git add -f captures/consolidation-acceptance-<robot>-<date>/notes.md
```

Exit 0 = all PASS; 2 = BLOCKED (record as UNVERIFIED); 1 = a real
failure. The program checks: a `MOVE_X` through the consolidated
`Link` carries its id and the camera confirms displacement (odometry
alone never does); the registered-mount heading is used unchanged
(a ~90 deg bearing error with clean pivots is the +90-applied-twice
signature); an out-of-bounds `Repositioner.go()` is refused with
nothing sent and an in-bounds one is not.

Preconditions are in sprint 034 ticket 013
(`clasi/sprints/done/034-*/tickets/done/013-*.md`): lights on, a
Terminal-launched aprilcam daemon, WiFi TCP or the radio relay
(WiFi drops under sustained motor load), no SSH to the robot Pis.

## Status probe at deferral (2026-09-06 ~02:30 PDT)

Read-only: Shelly `output: false` (lights off); an aprilcam daemon
process was running (pid 30344); a 4 s `dns-sd -B _robotlink._tcp`
browse produced no output (inconclusive -- the browse may not have
flushed). Nothing was commanded.
