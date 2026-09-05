#!/bin/zsh
set -u
R=reports/calibration-practice-20260905
C=(uv run python tests/calibration/calibrate.py)
COMMON=(--robot tigez --radio --camera hd-usb-camera --field-cm 110 70 --margin 15)
echo "== wait for tigez on camera 2 + radio"
n=0; until uv run python -c "
from aprilcam.mcp.connection import ConnectionManager
D=ConnectionManager().resolve(); t=[x for x in D.get_tags('hd-usb-camera').tags if x.tag.family.value=='apriltag' and x.tag.number==57 and x.world]
import sys; sys.exit(0 if t else 1)" 2>/dev/null || [ $n -ge 30 ]; do sleep 5; n=$((n+1)); done; echo "tag 57 seen after ~$((n*5)) s"
echo "== 1 dance"; $C turns $COMMON --dance-only 2>&1 | grep -vE "Uninstalled|Installed|warning|If " | tee $R/01-dance.log | tail -12
echo "== 2 turns lag sweep"; for L in 0 0.05; do $C turns $COMMON --angles 90 180 --reps 2 --cruise 0 --no-tlm --set lag=$L --out $R/02-turns-lag$L 2>&1 | grep -E "relay:|reconnect|STOP|Trace|^ *[0-9]+ +-?[0-9]+ " | tee $R/02-turns-lag$L.log; python3 -c "
import json; s=json.load(open('$R/02-turns-lag$L/summary.json')); print('lag $L:', {k:s.get(k) for k in ('n_turns','fit_gain','fit_offset_deg','mean_abs_err_deg','mean_drift_cm')}, {k:round(v['mean_err'],1) for k,v in s.get('per_command',{}).items()})"; done
echo "== 3 distance at lag 0.05"; $C distance $COMMON --lengths 200 300 --reps 1 --set lag=0.05 --travel-calib-now 0.78623 --out $R/03-distance 2>&1 | grep -vE "Uninstalled|Installed|warning|If " | tee $R/03-distance.log | grep -E "^ *[0-9]+ +[-+]|facing|STOP|fit_gain|travel_calib|mean_abs" 
echo "== 4 confirm 12 pivots at lag 0.05"; $C turns $COMMON --angles 90 107 180 --reps 2 --cruise 0 --no-tlm --set lag=0.05 --out $R/04-confirm-lag0.05 2>&1 | grep -E "relay:|reconnect|STOP|Trace|^ *[0-9]+ +-?[0-9]+ " | tee $R/04-confirm.log; python3 -c "
import json; s=json.load(open('$R/04-confirm-lag0.05/summary.json')); print('confirm:', {k:s.get(k) for k in ('n_turns','fit_gain','fit_offset_deg','mean_abs_err_deg','mean_drift_cm')}, {k:round(v['mean_err'],1) for k,v in s.get('per_command',{}).items()})"
echo "CHAIN-EXIT 0"
