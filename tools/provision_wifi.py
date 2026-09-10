#!/usr/bin/env python3
"""Provision a board's WIFICRED flash-backed credential store, in one
scripted bench session -- no hand-typed wire lines, no wizard UI (out
of scope for sprint 038 ticket 007; see that ticket's Description).

Wire grammar this wraps (MEASURED gopiv 2026-09-09/10,
captures/wifi-credential-store-20260909/notes.md; helpers in
tools/robotlink.py: wificred_set()/wificred_clear()/wificred_list()):

    WIFICRED SET <slot> <ssid> <password> #<id>  -> ack <id> ...
    WIFICRED #<id>                                 -> wificred <slot> <ssid> <haspw>
    WIFICRED CLEAR <slot> #<id>                    -> ack <id> ...

Slots are 0..7. `<password>` is mandatory on SET. The passphrase is
never readable back and this tool never prints, logs, or persists one
anywhere -- it is read once from an environment variable, a local
file, or (interactively) a non-echoing prompt, handed straight to
`WifiLink.send()`, and discarded.

**Provision AFTER flashing, not before.** A flash mass-erases the
whole chip (MEASURED gopiv 2026-09-09/10, same capture: an enumeration
of a store written before `mbdeploy deploy --remote gopiv` came back
empty after it), so credentials written before a deploy do not survive
it. This tool does not flash anything; run it as a separate step once
the board is already running the firmware you want.

Examples::

    # one slot, password from an env var (never on the command line,
    # never in shell history)
    WIFI_PW=hunter2example uv run python tools/provision_wifi.py \\
        --usb /dev/cu.usbmodem2121302 --slot 0 --ssid MyNetwork \\
        --password-env WIFI_PW

    # one slot, password from a local (gitignored) file's first line
    uv run python tools/provision_wifi.py --wifi gopiv --slot 0 \\
        --ssid MyNetwork --password-file ~/.secrets/mynetwork.txt

    # a board's whole list, one session, from a local (gitignored)
    # manifest -- see MANIFEST EXAMPLE below
    uv run python tools/provision_wifi.py --usb /dev/cu.usbmodem2121302 \\
        --manifest ~/.secrets/gopiv-wifi.json

    # read back what is stored (ssid + whether a password is set --
    # never the password itself)
    uv run python tools/provision_wifi.py --wifi gopiv --list

    # remove a slot
    uv run python tools/provision_wifi.py --wifi gopiv --clear 0

MANIFEST EXAMPLE -- a local, UNTRACKED file (never commit this; keep
it outside the repo or add its path to .gitignore), one entry per
slot to provision in this session::

    [
      {"slot": 0, "ssid": "MyNetwork", "password": "hunter2example"},
      {"slot": 1, "ssid": "SecondNetwork", "password": "hunter2example2"}
    ]
"""
import argparse
import getpass
import json
import os
import pathlib
import sys

import robotlink


def _password_from_args(a):
    """The passphrase for a single --slot/--ssid provisioning call --
    from --password-env, --password-file, or (neither given) an
    interactive, non-echoing prompt. Deliberately NO plain
    `--password` flag: a command-line argument is visible in `ps` and
    saved to shell history on most shells, exactly the leak this
    module exists to avoid."""
    if a.password_env:
        pw = os.environ.get(a.password_env)
        if pw is None:
            sys.exit(f'provision_wifi: ${a.password_env} is not set')
        return pw
    if a.password_file:
        text = pathlib.Path(a.password_file).read_text()
        pw = text.splitlines()[0] if text.splitlines() else ''
        return pw
    return getpass.getpass('WiFi password (not echoed): ')


def _open(a):
    if a.usb:
        return robotlink.open_link(port=a.usb)
    if a.radio:
        return robotlink.open_link(radio=True, robot=a.radio)
    return robotlink.open_link(wifi=a.wifi)


def _report(slot, lines):
    """Print a SET/CLEAR result -- the raw reply lines only, which the
    firmware never uses to carry a password (module docstring above),
    so nothing this prints can be one."""
    ok = any(t.startswith('ack ') for t in lines)
    err = next((t for t in lines if t.startswith('err ')), None)
    if err:
        print(f'slot {slot}: {err}')
    elif ok:
        print(f'slot {slot}: ok')
    else:
        print(f'slot {slot}: no reply ({lines})')
    return ok and not err


def provision_manifest(link, entries, wait=1.5):
    """Issue one `WIFICRED SET` per `entries` dict (each needs `slot`,
    `ssid`, `password`), in order, on the SAME session -- R6's "host
    tool can provision a board's whole list" framing. Returns True iff
    every entry's SET was accepted (ack, no err)."""
    ok = True
    for entry in entries:
        lines = robotlink.wificred_set(
            link, entry['slot'], entry['ssid'], entry['password'], wait=wait)
        ok = _report(entry['slot'], lines) and ok
    return ok


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    carrier = ap.add_mutually_exclusive_group(required=True)
    carrier.add_argument('--usb', metavar='PORT', help='local serial port')
    carrier.add_argument('--radio', metavar='ROBOT',
                         help="torture relay pool, tuned to this robot's "
                              'own channel/group')
    carrier.add_argument('--wifi', metavar='NAME|IP',
                         help="the robot's own WiFi TCP server; a name is "
                              'resolved by mDNS then broadcast')

    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument('--list', action='store_true',
                        help='enumerate the store and exit (ssid + whether '
                             'a password is set -- never the password)')
    action.add_argument('--clear', metavar='SLOT', type=int,
                        help='WIFICRED CLEAR this slot and exit')
    action.add_argument('--slot', metavar='SLOT', type=int,
                        help='WIFICRED SET this slot (needs --ssid and one '
                             'of --password-env/--password-file, else '
                             'prompts interactively)')
    action.add_argument('--manifest', metavar='PATH',
                        help='provision a whole list of slots in one '
                             'session from a local JSON file -- see this '
                             "module's docstring for the shape. NEVER "
                             'commit this file.')

    ap.add_argument('--ssid', help='SSID for --slot')
    ap.add_argument('--password-env', metavar='VAR',
                    help='env var holding the password for --slot')
    ap.add_argument('--password-file', metavar='PATH',
                    help="local file whose first line is --slot's password")
    a = ap.parse_args()

    if a.slot is not None and not a.ssid:
        ap.error('--slot needs --ssid')

    link = _open(a)
    try:
        if a.list:
            entries = robotlink.wificred_list(link)
            if not entries:
                print('(store empty)')
            for e in entries:
                print(f"slot {e['slot']}: {e['ssid']} "
                      f"(password set: {e['has_password']})")
            return 0

        if a.clear is not None:
            lines = robotlink.wificred_clear(link, a.clear)
            return 0 if _report(a.clear, lines) else 1

        if a.manifest:
            entries = json.loads(pathlib.Path(a.manifest).read_text())
            if not isinstance(entries, list) or not entries:
                sys.exit(f'provision_wifi: {a.manifest} must be a non-empty '
                         'JSON list -- see this module\'s docstring for '
                         'the shape')
            return 0 if provision_manifest(link, entries) else 1

        password = _password_from_args(a)
        lines = robotlink.wificred_set(link, a.slot, a.ssid, password)
        del password  # out of scope the instant it is no longer needed
        return 0 if _report(a.slot, lines) else 1
    finally:
        link.close()


if __name__ == '__main__':
    sys.exit(main())
