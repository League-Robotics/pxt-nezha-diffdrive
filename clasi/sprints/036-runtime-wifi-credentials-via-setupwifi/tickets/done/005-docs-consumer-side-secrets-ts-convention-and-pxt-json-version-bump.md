---
id: '005'
title: 'Docs: consumer-side secrets.ts convention, and pxt.json version bump'
status: done
use-cases:
- SUC-001
depends-on:
- '001'
- '002'
- '003'
- '004'
github-issue: ''
issue: wifi-credentials-are-set-in-code-from-the-project-s-own-secrets-ts.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Docs: consumer-side secrets.ts convention, and pxt.json version bump

## Description

Two independent, low-risk closing pieces of this sprint.

### 1. `docs/robot-connections.md` — the consumer-side `secrets.ts` convention

Per the issue's Proposal, this convention belongs in the project docs,
not in the extension itself (the extension only exposes the entry
point). Document, near wherever `docs/robot-connections.md` already
covers WiFi TCP as the default carrier (see
`.claude/rules/connecting-to-a-robot.md`'s summary of that doc's
content for where WiFi is already discussed):

- A student's own project keeps credentials in a gitignored
  `secrets.ts`, calling `diffDrive.setupWifi(WIFI_SSID,
  WIFI_PASSWORD)` from `on start` — exactly the shape
  `league-projects/scratch/nezha-robot-template/test/boot.ts` already
  has, one line, currently commented out pending this sprint.
- The project ships a TRACKED `secrets.example.ts` beside it (not
  gitignored), and the gitignored `secrets.ts` must still be listed in
  `pxt.json`'s `files` array — PXT compiles a fixed file set, so a
  listed-but-missing file breaks the build for anyone who clones
  without having copied the example first. State the one-line setup
  step explicitly: copy `secrets.example.ts` to `secrets.ts` and fill
  in real values.
- Note the scope limit explicitly, from the issue: this is a
  VS-Code-checkout convention only. The MakeCode web editor has no
  git, so a web-editor `secrets.ts` buys file separation from the
  tracked program but not actual secrecy.
- `setupWifi(ssid, password = "")` is hidden from the toolbox
  deliberately (not a beginner block) — mention why, briefly, so a
  reader doesn't go looking for it as a draggable block: a visible
  block would invite hardcoding a passphrase into a shared/tracked
  program, which is the exact thing this convention exists to prevent.

This is a documentation-only change. Do not edit
`league-projects/scratch/nezha-robot-template` — it is a separate
repo, out of scope for this sprint (its own restore is a one-line
change on its own side, already written and waiting on this release).

### 2. `pxt.json` version bump

This repo's release tags must outrank `v1.0.0` for MakeCode's
extension resolution — the scheme is `v1.YYYYMMDD.n`, not CLASI's
default `0.YYYYMMDD.n` `close_sprint` would otherwise apply. Per the
sprint's out-of-scope note, the stakeholder cuts the actual tag after
this sprint closes — this ticket's job is only to bump the `version`
field in `pxt.json` so a tag can be cut against it.

**Before touching `pxt.json`, check it is not already dirty from
another live session** (this is a SHARED checkout —
`.claude/rules/shared-checkout-has-other-live-sessions.md`): run `git
status --short pxt.json` first. If it shows modifications not from
this ticket's own work, STOP and report rather than bumping over
someone else's in-flight change.

Current version at ticket-creation time: `1.20260907.3`. Bump the
patch component following this repo's existing `1.YYYYMMDD.n` cadence
(bump `n` if today's date matches the existing value, otherwise reset
`n` to a fresh sequence for today's date — check `git log --oneline
-5` for the most recent bump commit's convention before choosing).

## Acceptance Criteria

- [x] `docs/robot-connections.md` documents the `secrets.ts` /
      `secrets.example.ts` convention, the `pxt.json` `files` listing
      requirement, the VS-Code-only secrecy caveat, and why
      `setupWifi()` is hidden from the toolbox.
- [x] `pxt.json`'s `version` field is bumped following this repo's
      existing `1.YYYYMMDD.n` convention, checked against a clean
      `git status --short pxt.json` immediately before the edit.
- [x] No change to `league-projects/scratch/nezha-robot-template` (out
      of scope, separate repo).
- [x] No change to `enableWifiLink()`'s behavior or to
      `tools/make_deploy.py::_inject_wifi_secrets()` (both explicitly
      out of scope for the whole sprint).

## Testing

- **Existing tests to run**: `tests/tools/test_make_deploy_wifi.py`
  (confirm the version bump doesn't perturb it — it shouldn't, since
  it targets the `kWifiSsid`/`kWifiPassword` regex, not the version
  field).
- **New tests to write**: none — this ticket is docs and a version
  string, not testable behavior.
- **Verification command**: `uv run pytest
  tests/tools/test_make_deploy_wifi.py`. The full suite runs once,
  inside `close_sprint`.
