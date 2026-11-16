# tests/dev — disposable scratch scripts

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-02 · **Status:** disposable

Scratch scripts that need a real robot, kept only while their
experiment is live. Nothing here is pytest, nothing runs in CI, and
nothing else in the repo depends on it.

A script that outlives its experiment either moves to
[`tests/system/`](../system/DESIGN.md) (it has become a repeatable
figure) or to `captures/<session>/` (it is now the record of one
measurement) — otherwise it is deleted.

Current contents: `closure.py` and `sweep_tcp.py`, copied from
`captures/gopiv-profile-sweep-20260901/` in the tour-suite
reorganisation (commit 248e846).

vevov turn/tour tuning, 2026-10-27/28 (camera-truthed on the main
playfield; logs in `captures/vevov-orange-dots-20261028/`):
`tag_dance.py` (checks the registered pose is the pivot centre),
`devlink.py` (serial-through-registry link, lit camera fixes, settle
waits), `pivot.py` (one pivot: asked vs encoders vs camera), `tour.py`
(open-loop rectangle), `dots.py` (camera pose onto each orange dot,
camera-corrected), `goto_tour.py` (the dot square by `GO_TO_W` after
one camera zero, scored by camera), `park.py` (centre to a point,
camera-guided) and `otos_probe.py` (encoder vs OTOS vs encoder-distance-
on-OTOS-heading pose, scored at every rest point).

OTOS characterisation, 2026-10-28 (logs in
`captures/vevov-otos-drift-20261028/`): `otos_arm.py` (fits where the
sensor sits from the circle it draws while pivoting) and `otos_drift.py`
(random go-tos for a set distance, never re-zeroed, logging camera,
odometry, OTOS and raw wheel counts at every stop).

Sprint 044 overnight acceptance, 2026-10-28/29 (logs and findings in
`captures/sprint044-acceptance-20261028/`, see its NOTES.md):
`peek.py` (read-only ID, STATUS and one TLM row), `otos_straight.py`
(forward/back straights: OTOS distance vs camera, no turns),
`otos_pivots.py` (in-place pivots: the OTOS centre track should not
move; fits the residual lever arm), `tlm_stream_move.py` (TLM FULL
through one move and the rest after it), `rest_hold.py` (stationary
hold on the idle read path, never commanded), `goto_probe.py` (GO_TO_W
legs with delayed TLM reads to expose a stale pose), `status_trace.py`
(STATUS active/done against wheel counts through one verb),
`disturb_watch.py` (a human bumps or lifts the resting robot; then a
GO_TO_W back to the estimator's start point) and
`sprint044_score.py` (scores an `otos_drift.py` log taken on sprint 044
firmware). `devlink.py` gained `DEVLINK_WIFI` and `send_move` now waits
for `done`, because `active` drops inside a GO_TO_W. `otos_drift.py`
gained `--xmin/--xmax` lanes so two robots can share the field.

Sprint 045 ticket 003 (logs and notes in `captures/sprint045-stored-radio-20261115/`):
`radiostore_accept.py` (bench acceptance of the stored radio address and `_reboot` on tovez: invalid sets,
set-then-reboot, reflash B then A, `reboot.fail`, raw-move reboot, clear; flashes by pyocd with a trimmed hex so the
settings survive). Its firmware is `test/radiostore_a.ts` and `test/radiostore_b.ts`, built with `make_deploy.py --program`.

`console_radio.mjs` (Node: sends a running robot-console's `radio-verify`, `radio-free-channels` and `radio-save`
websocket messages for one device and prints the answers).

The parent [`tests/DESIGN.md`](../DESIGN.md) table is the authority on
what each `tests/` subdirectory needs.
