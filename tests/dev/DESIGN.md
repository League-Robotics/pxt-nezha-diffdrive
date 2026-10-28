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

The parent [`tests/DESIGN.md`](../DESIGN.md) table is the authority on
what each `tests/` subdirectory needs.
