# Sprint 033 build checkpoint (ticket 009) -- desk build, 2026-09-06

Source: sprint branch `sprint/033-cohesion-odometry-object-config-descriptor-table-protocol-diet`
at commit 8af1326 (after ticket 008, the sprint's final source state), built in an
isolated detached worktree of that commit with `uv run python tools/make_deploy.py`
(no `--robot`, so no per-robot bake; V2/mbcodal only via csv-mbcodal).

Result: `binary-8af1326.hex`, 1 773 701 bytes, sha256 13fd99e86688a5dd..., attempt 1,
0 universal-hex block markers (plain V2 hex), all nezha-diffdrive translation units
compiled (make_deploy's stale-scratch checkpoint passed). Tail of the run in
`make_deploy.tail.txt`.

Same-session checks at the same commit:
- `uv run python tools/gen_config_field_enum.py --check` -> "src/blocks/motion.ts is up to date."
- `uv run pytest tests/host -q` -> 1147 passed in 50.29s

Intermediate desk builds of the same branch also passed on the first attempt after
tickets 002 (b7695e1), 003 (a58acb3), 004 (69dbccb), 005 (fe872a4), 006 (bfb704b)
and 007 (3c4575c); only the final hex is kept.

No hardware acceptance is claimed: nothing here was flashed or driven.
