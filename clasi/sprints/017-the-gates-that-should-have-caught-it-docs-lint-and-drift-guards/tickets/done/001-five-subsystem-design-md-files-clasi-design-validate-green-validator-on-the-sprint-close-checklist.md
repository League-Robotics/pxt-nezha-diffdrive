---
id: '001'
title: Five subsystem DESIGN.md files; clasi design validate green; validator on the
  sprint-close checklist
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: design-doc-set-fails-validation.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Five subsystem DESIGN.md files; clasi design validate green; validator on the sprint-close checklist

## Description

`clasi design validate` currently fails:

```
Missing design doc: subsystem directory src/blocks   has no DESIGN.md
Missing design doc: subsystem directory src/comms    has no DESIGN.md
Missing design doc: subsystem directory src/core     has no DESIGN.md
Missing design doc: subsystem directory src/motion   has no DESIGN.md
Missing design doc: subsystem directory src/platform has no DESIGN.md
```

`.clasi/config.yaml` declares `sources: [src, tools, tests, test]`. Sprint 013
grouped `src/` into five directories by dependency layer
(`core/`, `motion/`, `platform/`, `comms/`, `blocks/`); under the CLASI doc
model each becomes a subsystem directory needing a co-located `DESIGN.md`.
None was written, and sprint 013 ticket 006 (scoped as the sprint's final
sweep) did not run the validator. `docs/code-review/guidelines.md` states the
requirement directly: "The doc set must pass `clasi design validate`."

This ticket is doc-only. It does not touch `src/**/*.{h,cpp,ts}`.

## What to change

Write five thin `src/<dir>/DESIGN.md` files, following the pattern
`tests/DESIGN.md` -> `tests/host/DESIGN.md` already uses in this repo: a
short "Owner / Last reviewed / Status" header, a paragraph of scope (what
lives in this directory, at the one-sentence level), and a pointer into the
matching section of `src/DESIGN.md` for the fine-grained detail (the
directory split is coarser than the file-level detail `src/DESIGN.md`
carries, and that document's own preamble already says so -- these five
files just make each directory self-describing when a reader `ls`s into it,
they don't duplicate the content):

- `src/core/DESIGN.md` -> points at `src/DESIGN.md` S2 (Kernel) and the
  host-portable helper headers under S1's layer map (`heading_wrap.h`,
  `encoder_glitch_armor.h`)
- `src/motion/DESIGN.md` -> points at `src/DESIGN.md` S3 (Motion engine)
- `src/platform/DESIGN.md` -> points at `src/DESIGN.md` S7 (Hardware ports),
  including `encoder_pose_source.h`
- `src/comms/DESIGN.md` -> points at `src/DESIGN.md` S4-S6, S8 (Wire
  grammar, wire adapter, transports, protocol composition)
- `src/blocks/DESIGN.md` -> points at `src/DESIGN.md` S9 (Shim + blocks)

Do not restate the per-file detail in the new files -- if a reader needs
that, `src/DESIGN.md`'s section is the destination, exactly as
`tests/host/DESIGN.md` is the destination from `tests/DESIGN.md`. Keep each
file to roughly the size of `tests/host/DESIGN.md`'s own entry for a
sibling directory, not a fresh design document.

`src/DESIGN.md` itself needs one small edit: its preamble currently argues
past the validator failure ("the directory split is coarse... so it doesn't
carry the fine-grained detail below") without resolving it. Once the five
files exist, update that sentence to point at them instead of describing
the gap as still open.

Run `clasi design validate` and confirm `ok: true` before finishing.

**Recurrence guard**: add `clasi design validate` to the sprint-close
checklist so a future sprint that adds or renames a `src/` subsystem
directory cannot close without either adding its `DESIGN.md` or recording a
deliberate deviation. Find the sprint-close checklist (`docs/code-review/
guidelines.md`'s "Phase 0" section already states the requirement in prose;
locate wherever the mechanical pre-close checklist itself lives -- likely
referenced from the `close-sprint` skill or `review_sprint_pre_close`) and
add the validator invocation as an explicit, checkable step, not just prose
that can be skipped the way sprint 013 ticket 006 skipped it.

## Acceptance Criteria

- [x] `src/core/DESIGN.md`, `src/motion/DESIGN.md`, `src/platform/DESIGN.md`,
      `src/comms/DESIGN.md`, `src/blocks/DESIGN.md` exist, each with an
      Owner/Last-reviewed/Status header, a scope paragraph, and a pointer
      into the matching `src/DESIGN.md` section.
- [x] `src/DESIGN.md`'s preamble no longer argues past the validator gap --
      it points at the five new files.
- [x] `clasi design validate` returns `ok: true`.
- [x] The sprint-close checklist (wherever it lives) has `clasi design
      validate` as an explicit step, not implicit in prose.
- [x] No `src/**/*.{h,cpp,ts}` file is touched.

## Testing

- **Existing tests to run**: none -- doc-only change, no host test suite
  touches `src/DESIGN.md` or the new files. Confirm `uv run pytest
  tests/host/test_pxt_manifest_completeness.py` still passes (it does read
  `src/` but only for `.h`/`.cpp`/`.ts`, not `DESIGN.md`) as a sanity check
  that nothing else broke.
- **New tests to write**: none -- `clasi design validate` is itself the
  guard; it's an existing CLASI mechanism, not a new pytest test. The
  guard being added is procedural (the sprint-close checklist entry), not
  a new test file.
- **Verification command**: `clasi design validate` (expect `ok: true`).
