# tigez, gopiv, vevov onto the sprint-029 build (1.20260904.4), 2026-09-04 afternoon

Built from master 1b2c7f3 in the turn-calibration-029 worktree with
`make_deploy.py --robot <name> --radio-link` and config/wifi_secrets.json
present (`<name>-029-reflash-20260904/build.log`). Bakes: tigez
0.78623/114.4/0.9617/stop_distance 0; vevov 0.70066/128/0.987/stop_distance 0
(`pivot_overrun_mm` retired in radio-robot-lib 147f664); gopiv none.

| robot | via | flash | WiFi after | acceptance over WiFi TCP |
|---|---|---|---|---|
| tigez | farm meili | attempt 2 (probe timeout on 1) | immediately | 40/40 (`wifi-acceptance.log`) |
| gopiv | farm hodr | first try | immediately | 39/40 x2: GO_TO_W "wheels turned" misses repeatably on gopiv, passes on tigez; run 2 was clobbered by the run-1 TLM stream left on (`wifi-acceptance-{,2,3}.log`) |
| vevov | Pi nada on the field (null was out of power) | first try | immediately | see `reports/turn-cal-029-20260904/` |

vevov reflashed again the same afternoon with `lag_s 0.04` baked
(`build-lag.log`, `flash-lag-1.log`, hex sha256
42016c1aca679169e12667c0f96c1a7003fa3a1d977669015e8d5a5c4380f89f); post-flash
`GET`: lag 0.040, stop_distance 0, rotational_slip 0.987.
