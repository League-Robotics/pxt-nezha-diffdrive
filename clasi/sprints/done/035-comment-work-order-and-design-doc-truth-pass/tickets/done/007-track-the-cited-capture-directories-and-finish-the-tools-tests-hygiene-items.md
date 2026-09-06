---
id: '007'
title: Track the cited capture directories and finish the tools/tests hygiene items
status: done
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

- [x] A1 and A2: both directories force-tracked in full, no
      `__pycache__` added. `git ls-files` confirms.
- [x] A3: `notes.md`, `log.jsonl`, `radio-txcount-diagnostic.patch` and
      `fieldtour5.log.jsonl` tracked; the large JSON blobs are **not**.
- [x] A4: verified there is nothing to track; ticket 008's edit
      confirmed (or flagged as still outstanding if 008 has not run).
- [x] Every `captures/` path cited from `src/` (including
      `src/DESIGN.md`) resolves against `git ls-files` — demonstrate
      with the check below and paste its output into the completion
      notes.
- [x] B1: `tools/camlink.py`'s module docstring boiled down; the annex's
      own replacement recorded as rejected with its reason; no
      behaviour change in the file.
- [x] B2: `tests/host/test_kernel_harness.py`'s `compile_shared_lib`
      docstring replaced; the no-`-I` vs `include_dirs` distinction
      survives.
- [x] The ten already-applied tools-and-tests items and the one moot
      item are recorded as no-ops in the completion notes, naming
      sprint 034 and the `camproc.py` deletion.
- [x] The three out-of-scope untracked citations outside `src/` are
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

## Completion notes

### Part A — 37 files force-tracked, 197 KB total

| # | directory | files added | bytes | notes |
|---|---|---|---|---|
| A1 | `captures/gopiv-profile-sweep-20260901/` | 31 | 240K on disk | whole directory, added file-by-file from `find -type f`; no `__pycache__` present and none added |
| A2 | `captures/motion-profile-probe-20260901/` | 2 | 12K | `measured.txt`, `profile_probe.py` |
| A3 | `captures/tigez-cal-20260830/` | 4 | 28K | `notes.md`, `log.jsonl`, `radio-txcount-diagnostic.patch`, `fieldtour5.log.jsonl` only. The 17 remaining files (77K–462K JSON/JSONL blobs, 2.6M total) stay **untracked**, as specified |
| A4 | `captures/tovez-wifi-20260902/` | 0 | — | confirmed still absent from disk. **Ticket 008 has not run yet** — `src/DESIGN.md`'s dangling `captures/tovez-wifi-20260902/` path is still there, so this row is **outstanding until 008**. The same sentence's `docs/knowledge/2026-09-02-wifi-transport-tovez.md` is tracked, verified with `git ls-files` |

`git ls-files captures/ | grep -c __pycache__` → `0`. Total tracked
under `captures/` went 464 → 501. New bytes: `202150` (197 KB) across
the 37 files.

**Citation-resolution check** (the acceptance demonstration), run from
the repo root after the `git add -f`:

    captures/bench-acceptance-029-20260904c/             tracked=20
    captures/bench-acceptance-029-20260904d/             tracked=69
    captures/bench-acceptance-029-20260904d/heading-probe.log tracked=69
    captures/bench-acceptance-029-20260904d/notes.md     tracked=69
    captures/gopiv-floor70-20260829/                     tracked=14
    captures/gopiv-frozen-encoder-fix-20260902/notes.md  tracked=11
    captures/gopiv-profile-sweep-20260901/tour_tight.json tracked=31
    captures/motion-profile-probe-20260901/measured.txt  tracked=2
    captures/session-b-20260905/                         tracked=134
    captures/session-b-20260905/discriminator-20260905   tracked=134
    captures/session-b-20260905/discriminator-20260905/  tracked=134
    captures/session-b-20260905/discriminator-20260905/legs.json tracked=134
    captures/tigez-cal-20260830/notes.md                 tracked=4
    captures/tigez-radio-retest-20260902/                tracked=7
    captures/tovez-taper-20260829/variants.json          tracked=17
    captures/tovez-wifi-20260902/                        tracked=0

Every line is nonzero except `tovez-wifi-20260902/`, which is A4 — the
path ticket 008 drops in favour of the tracked
`docs/knowledge/2026-09-02-wifi-transport-tovez.md`. The check counts
per *directory*; a stricter per-*file* pass on the nine citations that
name a specific file (rather than a directory) shows all nine resolving
individually, including ticket 003's repointed
`captures/tigez-cal-20260830/notes.md`
(`src/platform/nezha_port.cpp` lines 23 and 85).

### Part B

**B1 — `tools/camlink.py` module docstring: boiled down, annex text
REJECTED.** The annex's row-6 replacement text was **not** pasted. Its
premise is gone: it prescribes a docstring for `ensure_registered()`,
and that function no longer exists in the file (the API is
`Cam.register()` / `Cam._register_one()`); its proposed text also
describes the `MOUNTS` table as the calibration of record, which is the
exact behaviour sprint 029 removed and which
`field_calibration.json` replaced. Pasting it would have re-introduced
a false statement. Recorded as **"replaced with different text, annex
text rejected because it cites a deleted function"**, per the ticket's
rules of engagement.

What was written instead — the current truth only:
`field_calibration.json` is the one calibration of record (TL-02);
constructing `Cam` registers nothing; registration is explicit via
`register()` / `--register`, once, when a mount actually changed;
an unregistered tag reports RAW while a **registered** tag's `yaw_rad`
IS the robot's heading already corrected (the REGISTERED-vs-RAW
distinction from `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
§"Registered vs raw", now stated explicitly as its own paragraph — it
was previously only implicit). Also dropped the sprint-034-ticket-008
narration of the deleted subprocess wrapper, keeping the live facts it
carried (in-interpreter daemon access, the background reader thread,
the `latest`/`fix()` stale-pose contract). Kept unchanged: the units
block, the fixed-convention paragraph and its rules-file path, the
6.4 cm parallax + 3.6 cm lever figure and its 2026-08-23 NE-orange-dot
ground truth, and the 2026-09-02 tag-53 remount incident (compressed,
not deleted). **No behaviour change** — docstring text only; TL-02's
registration semantics untouched.
`tests/tools/test_camlink.py::test_real_calibration_file_has_no_mounts_table_leftovers`
passed **before** and **after** the edit.

The two claims `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
flags against this file:

- **(a) "NOT persisted across a daemon restart" — already fixed, a
  no-op.** The docstring now reads "THE DAEMON DOES THE CORRECTING, AND
  IT REMEMBERS. Tag mount registrations persist across a daemon restart
  -- they are written to the daemon's mounts registry on disk and
  reload automatically at daemon startup." Nothing to fix. (The rules
  file's own description of camlink is therefore itself stale on this
  point; not edited — rules files are outside this ticket.)
- **(b) tag 57 (tigez) missing from `MOUNTS` — recorded, not fixed, and
  doubly moot.** There is no `MOUNTS` table in `camlink.py` any more
  (sprint 029 deleted it; the only surviving occurrence of the word is
  inside the docstring paragraph this ticket rewrote, and that mention
  is now gone too). And the calibration of record already carries
  tigez: `tools/field_calibration.json` has a `"tigez"` robot entry with
  `"tag_number": 57`, mount solved 2026-09-05
  (`reports/pf2-recal-20260905/08-mount-tigez/mount.json`). Data gap
  closed elsewhere; no action here.

**B2 — `tests/host/test_kernel_harness.py::compile_shared_lib`.** The
19-line `Sprint 017 ticket 009
(host-harness-masks-include-path-errors.md):` paragraph is gone,
replaced by the annex's row-8 one-liner expanded to keep the mechanism:
per-file `-c` compiles exist so the include path can differ per file —
production `src/` files compile with **NO** `-I` (as PXT does, so a
wrongly-spelled `src/`-internal include fails here exactly as it fails
the real build); `tests/host` shims get `include_dirs`. Docstring is
28 lines → 13. No behaviour change; `tests/host/test_kernel_harness.py`
5 passed.

### tools-and-tests annex: the eleven no-ops

Recorded, not re-applied. **Sprint 034** applied items **1, 2, 3, 4, 7,
9, 10, 11, 12, 13** (`robotlink.py` ×4, `tlm.py`, `leg_analysis.py`,
`tour_capture.py`/`test_tour_capture.py`, `make_deploy.py`,
`arc_capture.py`, `test_cxx11_syntax_gate.py`). Item **5** is **moot**:
`tools/camproc.py` was deleted, so its R-24/R-26 narrative has no host.
That leaves items **6** and **8** — B1 and B2 above — as the only live
ones, matching the sprint plan's verification pass (13 items, 2 live,
11 resolved-or-moot).

### Follow-up findings (recorded, NOT fixed here)

1. **Three capture citations outside `src/` still do not resolve** —
   out of scope, this sprint's acceptance is scoped to citations from
   `src/`:
   - `captures/vevov-cal-20260902` — present on disk, untracked.
   - `captures/vevov-line-20260902/deskew-clean.jpeg` — present on
     disk, untracked.
   - `captures/consolidation-acceptance-tigez-20260906` — **not
     present** on disk; needs repointing or the artifact producing.
2. **Two `MEASURED` claims in `test/test.ts` name no artifact**
   (reported by ticket 006; `test.ts` not edited here). Both are
   `.claude/rules/measurement-citations.md` defects of the same class
   this ticket serves:
   - line ~320: "MEASURED BUG, vevov 2026-08-25, against
     overhead-camera truth: four uncorrected corners cost 58 mm of tour
     closure that the robot scored as 22 mm" — no capture path.
   - line ~941: "MEASURED 2026-08-28 on vevov ... every one of 153
     frames read ox=oy=oh=0 while the encoders logged 246 mm of travel"
     — no capture path.
   (For contrast, the adjacent OTOS lever-arm claim at line ~282 *does*
   cite `captures/otos-run-handler-i2c-hang-20260828.md`, which is
   tracked — so the file is not uniformly deficient, only these two.)

### Tests (foreground, this turn)

    uv run pytest tests/tools/test_camlink.py::test_real_calibration_file_has_no_mounts_table_leftovers -q
      1 passed in 0.46s   (BEFORE the B1 edit)
      1 passed in 0.26s   (AFTER the B1 edit)
    uv run pytest tests/host/test_kernel_harness.py -q      → 5 passed in 1.80s
    uv run pytest tests/tools -q                            → 608 passed in 28.46s
    uv run pytest tests/host -q                             → 1167 passed in 32.12s
    uv run pytest tests/tools/test_ruff_clean.py -q         → 1 passed in 0.09s
