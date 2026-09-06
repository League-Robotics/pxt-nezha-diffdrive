---
id: '007'
title: Track the cited capture directories and finish the tools/tests hygiene items
status: in-progress
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Track the cited capture directories and finish the tools/tests hygiene items

## Description

Two small, unrelated jobs that share a property: neither touches
`src/`, so this ticket can run alongside 002-006 without a file
collision.

**No behaviour change.**

### Part A — make every `captures/` citation from `src/` resolve

`.claude/rules/measurement-citations.md`'s whole premise is that a
`MEASURED` claim names an artifact that can be checked. Six such
citations were reported unreachable; the verification pass re-derived
the set against the current tree and found **four** items, not six —
sprint 031 rewrote away every citation the review named from
`motion_engine.{h,cpp}`, and several directories have been force-added
since.

**`reports/` is not an option.** The 2026-09-03 brief offered "move the
number into a tracked `reports/*.md`" as an alternative. `.gitignore`
line 47 ignores `reports/` in full, so a tracked report does not exist
in this repo. **464 files under `captures/` are already force-tracked**
— that is the established precedent (alongside `docs/code-review/`),
and `git add -f` is the remedy.

| # | directory | cited from | on disk | tracked | action |
|---|---|---|---|---|---|
| A1 | `captures/gopiv-profile-sweep-20260901/` | `src/DESIGN.md`, `src/platform/nezha_port.cpp` | yes, 31 files, 240K | 0 | `git add -f` the whole directory — all `.json` and `.py`, largest file 78K |
| A2 | `captures/motion-profile-probe-20260901/` | `src/DESIGN.md` | yes, 2 files, 12K (`measured.txt`, `profile_probe.py`) | 0 | `git add -f` the whole directory |
| A3 | `captures/tigez-cal-20260830/` | `src/platform/nezha_port.cpp` | yes, 21 files, **2.6M** | 0 | track the small evidence only: `notes.md` (8.7K), `log.jsonl` (4.4K), `radio-txcount-diagnostic.patch` (4.7K), `fieldtour5.log.jsonl` (10K). Leave the 100-460K JSON blobs untracked. **Ticket 003 repoints the citation** at `notes.md`; verify it resolves |
| A4 | `captures/tovez-wifi-20260902/` | `src/DESIGN.md` | **does not exist** | — | nothing to track. The same sentence already cites `docs/knowledge/2026-09-02-wifi-transport-tovez.md`, which **is** tracked. **Ticket 008 drops the dangling path** and keeps the tracked doc; verify |

Verify before acting and again after. Every other `captures/` path
cited from `src/` was checked at planning time and is fully tracked:
`bench-acceptance-029-20260904c/` (20), `…-20260904d/` (69),
`session-b-20260905/` (134), `gopiv-floor70-20260829/` (14),
`gopiv-frozen-encoder-fix-20260902/` (11),
`tigez-radio-retest-20260902/` (7),
`tovez-taper-20260829/variants.json` (tracked; only `__pycache__/` is
not, and that should stay untracked).

**`__pycache__` never gets force-added.** `git add -f` on a directory
will happily sweep it in. Add files explicitly or filter.

Out of scope but worth recording in the completion notes as a
follow-up, **not** fixed here: three further untracked or dangling
capture citations exist outside `src/` —
`captures/vevov-cal-20260902` and
`captures/vevov-line-20260902/deskew-clean.jpeg` (both present,
untracked) and `captures/consolidation-acceptance-tigez-20260906` (not
present). This sprint's acceptance is scoped to citations from `src/`.

### Part B — the two surviving tools/tests hygiene items

The tools-and-tests annex
(`docs/code-review/2026-09-02/raw/tools-and-tests.md`, "Comment /
docstring hygiene") listed 13 items. **Sprint 034 applied ten**
(1, 2, 3, 4, 7, 9, 10, 11, 12, 13) and **item 5 is moot** —
`tools/camproc.py` was deleted. Verified at planning time. Two survive:

**B1 — `tools/camlink.py`'s module docstring (annex item 6).** LIVE as a
boil-down, **not** as the annex writes it. The annex's replacement text
is itself now stale: it prescribes a docstring for
`ensure_registered()`, and that function no longer exists — the API is
`Cam.register()` / `Cam._register_one()`. The current text is a 15-line
sprint-029 narrative that *correctly* explains what the old behaviour
was and why it was removed:

    **Sprint 029 (TL-02): `field_calibration.json` is the one calibration
    of record.** Constructing `Cam` never registers anything -- the old
    `MOUNTS` table and `Cam.__init__`'s unconditional `ensure_registered()`

Boil it down to what a reader needs *now*: `field_calibration.json` is
the calibration of record; constructing `Cam` registers nothing;
registration is explicit via `register()` or `--register`; an
unregistered tag reports RAW. **Do not paste the annex's replacement**
— record that you rejected it and why. **Do not change any behaviour in
`camlink.py`**: TL-02 is a separate, still-open finding about
registration semantics and is out of scope here.

While you are in the file, check the two claims
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md` flags against
it: (a) that mount registrations are "NOT persisted across a daemon
restart" — stale, they are written to
`state_dir/mounts/registry.json`; (b) that the `MOUNTS` table lacks an
entry for tag 57 (tigez). If (a)'s stale claim is still in the file,
fix the text — it is the same defect class. (b) is a data gap, not a
comment defect; record it, do not fix it.

**B2 — `tests/host/test_kernel_harness.py` (annex item 8).** LIVE
verbatim as the annex describes: `compile_shared_lib`'s docstring
carries a `Sprint 017 ticket 009
(host-harness-masks-include-path-errors.md):` paragraph. Replace with
the annex's one-liner: production `src/` files compile with **no** `-I`
(as PXT does); `tests/host` shims get `include_dirs`. That distinction
is the whole reason the function exists — keep it, drop the ticket
narration.

### Rules of engagement

- Re-anchor by quoted content, never by line number.
- A replacement whose premise changed is a **recorded no-op**, never
  forced. B1 is exactly this case and the annex row for it must be
  recorded as "replaced with different text, annex text rejected
  because it cites a deleted function".
- `.claude/rules/measurement-citations.md` — this ticket exists to
  serve it; do not delete an artifact path anywhere.

## Acceptance Criteria

- [ ] A1 and A2: both directories force-tracked in full, no
      `__pycache__` added. `git ls-files` confirms.
- [ ] A3: `notes.md`, `log.jsonl`, `radio-txcount-diagnostic.patch` and
      `fieldtour5.log.jsonl` tracked; the large JSON blobs are **not**.
- [ ] A4: verified there is nothing to track; ticket 008's edit
      confirmed (or flagged as still outstanding if 008 has not run).
- [ ] Every `captures/` path cited from `src/` (including
      `src/DESIGN.md`) resolves against `git ls-files` — demonstrate
      with the check below and paste its output into the completion
      notes.
- [ ] B1: `tools/camlink.py`'s module docstring boiled down; the annex's
      own replacement recorded as rejected with its reason; no
      behaviour change in the file.
- [ ] B2: `tests/host/test_kernel_harness.py`'s `compile_shared_lib`
      docstring replaced; the no-`-I` vs `include_dirs` distinction
      survives.
- [ ] The ten already-applied tools-and-tests items and the one moot
      item are recorded as no-ops in the completion notes, naming
      sprint 034 and the `camproc.py` deletion.
- [ ] The three out-of-scope untracked citations outside `src/` are
      recorded as a follow-up, not fixed.

## Testing

Foreground only.

- **Citation resolution check** (the acceptance demonstration; run from
  the repo root):

      for d in $(grep -rhoE 'captures/[A-Za-z0-9._/-]+' src/ | sort -u); do
        base=$(echo "$d" | cut -d/ -f2)
        printf "%-52s tracked=%s\n" "$d" \
          "$(git ls-files "captures/$base" | wc -l | tr -d ' ')"
      done

  Every line must show a nonzero count, except the one repointed at
  `docs/knowledge/2026-09-02-wifi-transport-tovez.md`.

- **Existing tests to run**:

      uv run pytest tests/host/test_kernel_harness.py -q
      uv run pytest tests/tools/ -q
      uv run pytest tests/host/ -q

  `tests/tools/test_camlink.py` includes
  `test_real_calibration_file_has_no_mounts_table_leftovers`, which
  reads `camlink.py`'s text — run it before and after the B1 edit.

- **New tests to write**: none.
- **Verification command**: `uv run pytest tests/host/ tests/tools/ -q`

## Notes for the implementer

- Replacement text source:
  `docs/code-review/2026-09-02/raw/tools-and-tests.md`, "Comment /
  docstring hygiene", rows 6 and 8 (row 6's text rejected — see B1).
- Read `sprint.md`'s "Verification pass" section first; its
  "Capture citations" table is the authority for Part A.
- Do not run the full repo suite.
