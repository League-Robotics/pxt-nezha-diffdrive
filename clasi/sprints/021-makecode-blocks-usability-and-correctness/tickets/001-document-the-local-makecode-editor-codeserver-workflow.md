---
id: '001'
title: Document the local MakeCode editor (codeserver) workflow
status: open
use-cases: [SUC-006]
depends-on: []
github-issue: ''
issue: document-the-local-makecode-editor-workflow.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Document the local MakeCode editor (codeserver) workflow

## Description

Write `docs/local-editor.md`, capturing the local pxt-serve/codeserver
workflow that a 2026-08-25 evening session reverse-engineered from
scratch and that currently lives only in that session's memory notes.
This is deliberately ticket 001: every other ticket in this sprint
verifies its own work through this same local editor (and, for the
sim.ts and radio-group tickets, through a `pxt build` + `mbdeploy`
hardware flash), so writing the workflow down first gives every later
ticket a checked reference instead of re-deriving it from the issue
text. Runs first, before any other ticket.

Docs-only — not gated by the source-code ticket rule (`.claude/rules/
source-code.md` excludes `docs/` and `*.md`), but tracked as a ticket
anyway for traceability against SUC-006 and the linked issue.

## Acceptance Criteria

- [ ] `docs/local-editor.md` exists and covers all seven points from
      `document-the-local-makecode-editor-workflow.md`:
      1. Serving: `pxt serve --noBrowser --noauth --noSerial` from the
         repo root; note the harmless "scandir 'libs'" startup message.
      2. Seeing local projects: `http://localhost:3232/index.html?ws=fs`
         — explain the `?ws=fs` filesystem workspace, that projects live
         in `<serve-cwd>/projects/` (one folder per `pxt.json`), and the
         double-navigate requirement (first load consumes the auth token
         and drops the query string).
      3. Testing blocks via a consumer project depending on the
         extension by `file:` path (the extension itself opens JS-only).
      4. The 1-4 minute first-open freeze on a project using the
         extension (main-thread typecheck) — not a hang.
      5. The `_history` auto-save wedge: symptom ("Project Auto-Save
         Disabled"), cause (a 409 conflict), and recovery (delete
         `_history`, close other editor clients, reload).
      6. Flashing: why MakeCode's Download (universal hex) is unsafe
         here (unparseable by mbdeploy/pyocd, mass-erases the board on a
         failed flash) and the safe alternative (`pxt build` for a plain
         V2 hex, then `mbdeploy`); note that a browser tab holding a
         WebUSB pairing must be parked first ("Unable to claim
         interface").
      7. The remote-testing pattern: `on run "name"` blocks triggered by
         cleartext `RUN:name` over serial (no `#id` needed — the v6
         sequenced path is a different parser); library dispatch emits
         no receipt, so behavior is proved via `TLM POSE #1` frames or
         `diffDrive.emitLine()` receipts, not a RUN acknowledgment.
- [ ] The scaffold embedded in the issue (`.claude/launch.json`,
      `projects/blocktest/pxt.json`, `main.blocks`, `main.ts`) is
      reflected in the doc, adjusted for whatever `projects/` actually
      contains today (see Open Question 3 in this sprint's Architecture
      section — confirm before writing whether `projects/` needs to be
      created by the reader or already exists, gitignored, on master).
- [ ] README gets a pointer to `docs/local-editor.md` (a short link, not
      a duplicate of its content).
- [ ] A fresh reader (not the original 2026-08-25 session) can follow
      the doc end-to-end: serve, see a disk project, build, and flash,
      without asking a question the doc doesn't already answer.

## Implementation Plan

**Approach**: Confirm the current on-disk state of `.claude/launch.json`
and `projects/` (both reportedly already on master per the issue) before
writing, so the doc describes what a reader actually finds rather than
what the original session set up from scratch. Write `docs/local-editor.md`
in prose + verified command blocks, structured around the seven points
above in the order a reader would hit them (serve -> see projects -> test
blocks -> patience -> `_history` recovery -> flash -> remote-test). Add
one README line pointing at it.

**Files to create/modify**:
- `docs/local-editor.md` (new)
- `README.md` (one new pointer line)
- Verify (do not necessarily recreate) `.claude/launch.json` and
  `projects/` scaffold state; note discrepancies in the doc rather than
  silently changing them, unless they're missing entirely.

**Testing plan**: Follow the doc's own steps end-to-end as the
verification — serve, `?ws=fs` double-navigate, open a project using the
extension, hit (or confirm absence of) the `_history` wedge, build a
plain hex, flash via `mbdeploy` to either vevov (via zavaz relay) or
tovez (USB only), and confirm a `RUN:` verb round-trips. This IS the
test; no `uv run pytest` coverage applies to a docs-only ticket, but
`uvx ruff check tools tests` and the other repo-wide gates still apply
if any tooling file is touched (none expected here).

**Documentation updates**: `docs/local-editor.md` (new), `README.md`
(pointer).
