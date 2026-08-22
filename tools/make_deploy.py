#!/usr/bin/env python3
"""Build a flashable hex from the repo, in a scratch copy.

`pxt build` in the repo does NOT put the test program in the hex:
`test.ts` lives in `testFiles`, and it has to stay there, because a
`files`-listed test would run inside every student project that
installs this extension.

So deploys go through a scratch copy where `test/test.ts` is promoted
into `files`. That copy used to be maintained by hand, and it drifted:
it omitted `testrig.ts` entirely, which is how that file sat
uncompilable without anyone noticing. Generating it from the repo's own
manifest is the fix -- there is nothing left to forget to copy.

  uv run python tools/make_deploy.py            # build
  uv run python tools/make_deploy.py --flash    # build, then flash vevov

Two traps this script exists to avoid, both of which cost hours:

* `disablesVariants: ["mbdal"]` is dropped. In a top-level project it
  produces a hex that is DEAD ON THE DEVICE. The repo keeps it (it is
  an extension, where it is fine and skips a pointless V1 build); the
  deploy copy must not. The price is a V1 `TS9283 program too big`
  error, which is expected and harmless.
* That TS9283 error aborts packaging NONDETERMINISTICALLY, and when it
  does it DELETES the hex rather than leaving a stale one. The hex is
  removed up front and its existence checked afterwards, so a failed
  package can never be mistaken for a good build.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(REPO, '.tmp', 'deploy-head')
HEX = os.path.join(DEPLOY, 'built', 'mbcodal-binary.hex')
ELITE = '/Volumes/Proj/proj/RobotProjects/radio-robot-elite'


def sync():
    manifest = json.load(open(os.path.join(REPO, 'pxt.json')))
    os.makedirs(DEPLOY, exist_ok=True)

    # node_modules by symlink (big); pxt_modules by copy (pxt writes it)
    link = os.path.join(DEPLOY, 'node_modules')
    if not os.path.islink(link):
        if os.path.exists(link):
            shutil.rmtree(link)
        os.symlink(os.path.join(REPO, 'node_modules'), link)
    dst = os.path.join(DEPLOY, 'pxt_modules')
    if not os.path.exists(dst):
        shutil.copytree(os.path.join(REPO, 'pxt_modules'), dst)

    # Every file the repo declares, at its declared path, plus the test
    # program promoted so the hex actually has the button handlers.
    files = list(manifest['files'])
    promoted = [f for f in manifest.get('testFiles', [])
                if f.endswith('test.ts')]
    for rel in files + promoted:
        src = os.path.join(REPO, rel)
        out = os.path.join(DEPLOY, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        shutil.copy2(src, out)

    manifest['files'] = files + promoted
    manifest['testFiles'] = []
    manifest.pop('disablesVariants', None)      # see module docstring
    json.dump(manifest, open(os.path.join(DEPLOY, 'pxt.json'), 'w'),
              indent=4)
    return files + promoted


def build():
    if os.path.exists(HEX):
        os.remove(HEX)          # so an aborted package cannot look fresh
    subprocess.run(['pxt', 'build'], cwd=DEPLOY, check=False)
    if not os.path.exists(HEX):
        sys.exit('BUILD PRODUCED NO HEX -- packaging aborted (see TS9283 '
                 'note in this file). Just run it again.')
    print(f'hex: {HEX}  ({os.path.getsize(HEX)} bytes)')


def flash(name):
    r = subprocess.run(['mbdeploy', 'deploy', name, '--hex', HEX],
                       cwd=ELITE)
    if r.returncode != 0:
        print('\nmbdeploy failed. The proven fallback is DAPLink mass '
              'storage: match the board UID in /Volumes/MICROBIT*/'
              'DETAILS.TXT and copy the hex onto that drive.')
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--flash', action='store_true')
    ap.add_argument('--robot', default='vevov')
    a = ap.parse_args()
    for f in sync():
        print(f'  {f}')
    build()
    if a.flash:
        flash(a.robot)


if __name__ == '__main__':
    main()
