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

The parent [`tests/DESIGN.md`](../DESIGN.md) table is the authority on
what each `tests/` subdirectory needs.
