---
status: pending
sprint: '021'
---

# Document the local MakeCode editor (codeserver) workflow

## Problem

Getting the extension's blocks into a locally-served MakeCode editor
and a student-style program onto a robot required a full evening of
reverse-engineering (2026-08-25). None of it is written down in the
repo; the knowledge currently lives in one session's memory notes.

## What the doc must cover (all verified working)

1. Serve: `pxt serve --noBrowser --noauth --noSerial` from the repo
   root; the "scandir 'libs'" startup error is harmless.
2. See local projects: open
   `http://localhost:3232/index.html?ws=fs` — the `?ws=fs` filesystem
   workspace is what makes disk projects appear; projects live in
   `<serve-cwd>/projects/` (one folder per pxt.json). The first page
   load consumes the auth token and DROPS the query string — navigate
   twice.
3. Test blocks via a consumer project with
   `"nezha-diffdrive": "file:../nezha-diffdrive"` — the extension
   itself opens JS-only.
4. Patience: first open of a project using the extension freezes the
   tab 1–4 minutes (main-thread typecheck). It is not hung.
5. Auto-save wedge: a 409 conflict on the editor's `_history` file
   silently drops the workspace to memory ("Project Auto-Save
   Disabled") and edits stop reaching disk — delete `_history`,
   close other editor clients, reload.
6. Flashing: MakeCode's Download produces a UNIVERSAL hex that
   pyocd/mbdeploy cannot parse (and its failure path mass-erases the
   board). Build instead with `pxt build` in the project folder and
   flash the plain V2 hex via mbdeploy. A browser tab holding a
   MakeCode WebUSB pairing claims the DAP interface — park the tab
   before flashing ("Unable to claim interface" is the symptom).
7. Remote-testing pattern: bind programs to `on run "name"` blocks and
   trigger with cleartext `RUN:name` over serial (no #id needed);
   library dispatch emits no receipt — prove behavior with
   `TLM POSE #1` pose frames or `diffDrive.emitLine()` receipts.

A working `.claude/launch.json` codeserver entry and a populated
`projects/` scaffold exist on the `claude/blocks-local-codeserver-test-bf93c6`
branch to crib from. Deliverable: a doc under `docs/` (e.g.
`docs/local-editor.md`) plus README pointer.
