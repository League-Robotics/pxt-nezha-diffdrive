# Sprint 035 desk build checkpoint -- 2026-09-06

Sprint 035 is comment/documentation only; this build is its gate for the
pxt.h-bound translation units (shims.cpp, protocol.*, the transports,
platform/) that the host suite cannot compile.

Built with `uv run python tools/make_deploy.py` (no --robot) in an
isolated detached worktree of the sprint's final source commit 3c5c05d:
binary.hex 1 709 936 bytes, sha256 6259413ddf63bcd8..., attempt 1, 0 universal-hex
block markers, all nezha-diffdrive translation units compiled.
An earlier desk build after ticket 003 (commit acf3396, the shims.cpp
edits) also passed on attempt 1.

The hex is 63 765 bytes smaller than sprint 033's checkpoint
(captures/sprint-033-build-checkpoint-20260906/, 1 773 701 bytes)
because MakeCode embeds the project's TypeScript source in the hex and
this sprint removed comment lines from src/blocks/*.ts and test/test.ts.
The hex itself is not kept; comment edits are not behaviour and the
sprint-033 checkpoint hex remains the flashable reference.

No hardware acceptance is claimed.
