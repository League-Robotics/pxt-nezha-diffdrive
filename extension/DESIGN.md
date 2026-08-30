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
through, so **the version here is the release there**: the sync pushes
a `v<version>` tag when that tag does not yet exist.

## Cutting a release

`config/dotconfig.yaml` is the project's single source of truth for the
version. `pxt.json` MIRRORS it and is never edited by hand;
`publish_extension.py` refuses to assemble when the two disagree, so a
version cannot be invented.

```sh
dotconfig version bump --major 1     # config + pyproject + package.json
python3 tools/publish_extension.py --sync-version   # -> pxt.json
git commit -am "Release <version>" && git push      # the Action tags it
```

**`--major 1` is not optional.** MakeCode resolves an extension by its
HIGHEST SEMVER TAG, and the extension repo carries `v1.0.11` from its
first releases. A `0.YYYYMMDD.n` tag sorts BELOW that, so the release
would succeed, tag cleanly, and reach nobody — a silent failure, which
is why `check_version()` refuses a major of 0 outright rather than
warning. `--major 1` keeps dotconfig's date scheme while outranking
every `v1.0.x`: `1.20260829.1` > `1.0.11` because 20260829 > 0. This is
the trap commit 07e1e87 named, "extension semver must outrank the
firmware's 0.YYYYMMDD.n tags". Tags are
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
