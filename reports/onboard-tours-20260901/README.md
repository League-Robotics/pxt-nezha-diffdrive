# On-robot tour programs — a FAILED run, kept as evidence

This directory is **not** a set of results. It holds the telemetry
captured while `RUN:square:30` reset the board on gopiv, 2026-09-01,
and it exists only to back
`clasi/issues/run-fiber-motion-resets-the-board-on-fw-1-20260829-1.md`.

`square.json` covers 3.3 s and 60 frames. The last frame reads
x = 299 mm of a commanded 300 mm leg with the wheels still turning
(`vl=36 vr=46`) — the stream stops dead there because the board
resets. `square.png` charts that fragment, so its path is one leg of a
square and its "closure 299.0 mm" is the leg length, not a score.

There are no `infinity` or `spline` captures: the harness never got
past the first program.

Working tour results for the same figures, driven from the host over
`MOVE_X`, are in `../tours-20260901/` and `../tours-20260901.md`.
