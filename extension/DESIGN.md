# extension — overlay for the published MakeCode extension

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-29 · **Status:** new

The extension students install lives in its own repository,
<https://github.com/League-Microbit/pxt-diff-drive>, which is
**generated** from this one by `tools/publish_extension.py` on every
push to master (`.github/workflows/publish-extension.yml`). Nothing is
edited there; anything that should change there changes here.

The published tree is the union of two things:

1. **`pxt.json`'s `files` list** — copied at the same relative paths.
   This is exactly what PXT ships to a consuming project, so the
   published extension is by construction the one this repo builds.
2. **This directory** — files that exist ONLY in the published repo.
   `README.md` here is the student-facing extension README and
   **replaces** the engineering README `files` also lists (the script
   refuses to publish if this overlay has no README). `LICENSE`,
   `tsconfig.json`, `.gitignore` and `.github/workflows/makecode.yml`
   (the extension repo's own build check, V2-only via
   `PXT_COMPILE_SWITCHES=csv-mbcodal`) are the standard MakeCode
   extension scaffolding. Every `*.ts` at this directory's root becomes
   a published `testFiles` entry — `test.ts` is the small sample
   program MakeCode opens with the repo — so this repo's own
   `test/test.ts` bench console is deliberately NOT published.
   `DESIGN.md` (this file) is excluded.

The published `pxt.json` is this repo's with `testFiles` rewritten to
the overlay's and `"public": true` added; everything else passes
through, so **bumping `version` here is a release there**: the sync
pushes a `v<version>` tag when that tag does not yet exist. Tags are
never moved — MakeCode pins projects to a tag and caches the compiled
native code under it — so a content change without a bump lands on
the branch only and the job summary says so.

Auth is a write **deploy key** on the extension repo whose private half
is this repo's `PXT_DIFF_DRIVE_DEPLOY_KEY` Actions secret. It can push
to that one repository and nothing else. To rotate: `ssh-keygen -t
ed25519`, `gh repo deploy-key add --allow-write` on the extension repo,
`gh secret set` here.

Try it without pushing: `python3 tools/publish_extension.py` lists the
tree; `--out DIR` writes it; `--publish --dry-run` does everything but
push. `tests/tools/test_publish_extension.py` runs the whole publish
path against a local bare repo.
