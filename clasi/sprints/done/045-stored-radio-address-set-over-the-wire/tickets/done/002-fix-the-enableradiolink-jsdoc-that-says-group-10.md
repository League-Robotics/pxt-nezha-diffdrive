---
id: '002'
title: Fix the enableRadioLink JSDoc that says group 10
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: run-ts-jsdoc-still-says-radio-group-10.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix the enableRadioLink JSDoc that says group 10

## Description

`src/blocks/run.ts`, the `enableRadioLink()` doc block: the continuation
line `time -- and group 10.` is stale. Replace it with the true statement
that the radio uses the channel and group `tools/make_deploy.py` injected
for that board. Do not change `setupRadio`'s `group: number = 10` default or
its "defaults to 10" JSDoc, which is still true. JSDoc is student-facing
block help; edit text only.

## Acceptance Criteria

- [x] The stale "and group 10" claim is gone from `enableRadioLink()`'s doc.
- [x] No code change; `setupRadio` default untouched.
- [x] `test_typescript_typecheck.py` and `test_block_toolbox_order.py` pass.

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_typescript_typecheck.py tests/host/test_block_toolbox_order.py`
- **New tests to write**: none
- **Verification command**: `uv run pytest tests/host`
