#!/bin/zsh
R=reports/vevov-recal-20260905
C=(uv run python tests/calibration/calibrate.py)
COMMON=(--robot vevov --wifi vevov --camera hd-usb-camera --field-cm 110 70 --margin 15)
F='grep -vE "Uninstalled|Installed|warning|If "'
echo "== 1 dance (turns only: the field is shared)"
$C turns $COMMON --dance-only --dance-turns-only 2>&1 | grep -vE "Uninstalled|Installed|warning|If " | tee $R/01-dance.log | tail -8
echo "== 2 mount (tag 12.4 cm, probe east)"
$C mount $COMMON --mount-z 12.4 --pivots 8 --probe 300 --face 0 --write --out $R/02-mount 2>&1 | grep -vE "Uninstalled|Installed|warning|If " | tee $R/02-mount.log | grep -vE "^\s+\"|^\s+\]|^\s+\[|^\s+[-0-9.]+,?$"
echo "== 3 distance (new wheels)"
$C distance $COMMON --lengths 200 300 400 --reps 2 --travel-calib-now 0.70066 --out $R/03-distance 2>&1 | grep -vE "Uninstalled|Installed|warning|If " | tee $R/03-distance.log | grep -E "^ *[0-9]+ +[-+]|facing|STOP|fit_gain|fit_offset|travel_calib|mean_abs|mean_err|Trace"
echo "== 4 turns: lag sweep"
for L in 0 0.04 0.10; do $C turns $COMMON --angles 90 180 --reps 2 --cruise 0 --no-tlm --set lag=$L --out $R/04-turns-lag$L 2>&1 | grep -E "relay:|reconnect|STOP|Trace|^ *[0-9]+ +-?[0-9]+ " | tee $R/04-turns-lag$L.log; python3 -c "
import json; s=json.load(open('$R/04-turns-lag$L/summary.json')); print('lag $L:', {k:s.get(k) for k in ('n_turns','fit_gain','fit_offset_deg','mean_abs_err_deg','mean_drift_cm')}, {k:round(v['mean_err'],1) for k,v in s.get('per_command',{}).items()})"; done
echo "CHAIN-EXIT 0"
