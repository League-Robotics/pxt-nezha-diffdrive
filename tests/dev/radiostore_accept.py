"""Bench acceptance of the stored radio address and _reboot (sprint 045 ticket 003).

Needs tovez on USB and its serial lock free. Writes one capture file per step
into captures/sprint045-stored-radio-<date>/. Wheel-free except `moveboot`,
which sends one short MOVE_X with the robot on its stand.

    uv run --with intelhex python tests/dev/radiostore_accept.py all
    uv run python tests/dev/radiostore_accept.py start|baseline|invalid|set_reboot|flash_b|flash_a|busy|queued|moveboot|clear
"""
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MBTOOLS = REPO.parent / 'mbtools'
OUT = REPO / 'captures' / 'sprint045-stored-radio-20261115'
HEX = {'a': REPO / '.tmp' / 'radiostore_a.hex', 'b': REPO / '.tmp' / 'radiostore_b.hex'}
ROBOT = 'tovez'
UID = '9906360200052820a8fdb5e413abb276000000006e052820'
CHANNEL = 77
GROUP = 29
counter = [len(list(OUT.glob('[0-9][0-9]-*.txt'))) if OUT.exists() else 0]


def session(name, steps, tail=2.0, reset=False):
    """steps: (line, seconds to wait after it). Writes the capture and returns its text."""
    counter[0] += 1
    proc = subprocess.Popen(['uv', 'run', 'mbserial', *(['--reset'] if reset else []), '--timeout', str(tail), ROBOT],
                            cwd=MBTOOLS, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    stamp = time.strftime('%H:%M:%S')
    for line, wait in steps:
        proc.stdin.write(line + '\n')
        proc.stdin.flush()
        time.sleep(wait)
    out, _ = proc.communicate(timeout=60)
    lines = [l for l in out.splitlines() if not l.startswith('DBG:wifi')]
    path = OUT / f'{counter[0]:02d}-{name}.txt'
    path.write_text(f'# {stamp} {name}\n# sent: {[s[0] for s in steps]}\n' + '\n'.join(lines) + '\n')
    print(f'--- {path.name}')
    print('\n'.join(lines))
    return '\n'.join(lines)


def hello():
    return ('HELLO', 1.2)


def flash(which):
    """Straight pyocd, never mbdeploy. On tovez the full-hex erase fails (0x67 at
    sector 0, or a probe timeout) and mbdeploy's mass-erase recovery then wipes
    the stored settings this test is about. The flash keeps the settings only
    when sector 0 and the UICR record are left out of the hex and the core is
    halted for the erase, so the hex is trimmed to 0x1000..0x80000 first."""
    from intelhex import IntelHex
    counter[0] += 1
    full = IntelHex(str(HEX[which]))
    trimmed = IntelHex()
    for addr in full.addresses():
        if 0x1000 <= addr < 0x80000:
            trimmed[addr] = full[addr]
    trim_path = HEX[which].with_name(HEX[which].stem + '_trim.hex')
    trimmed.write_hex_file(str(trim_path))
    log = []
    for attempt in range(1, 4):
        r = subprocess.run(['uv', 'run', 'python', '-m', 'pyocd', 'flash', '-t', 'nrf52833', '--uid', UID,
                            '--connect', 'halt', '--erase', 'sector', str(trim_path)],
                           cwd=MBTOOLS, capture_output=True, text=True)
        text = (r.stdout + r.stderr).replace('\r', '\n')
        text = '\n'.join(l for l in text.splitlines() if l.strip() and not l.startswith('['))
        log.append(f'## attempt {attempt} rc {r.returncode}\n{text}')
        if r.returncode == 0:
            break
        time.sleep(10)
    (OUT / f'{counter[0]:02d}-flash_{which}.txt').write_text(f'# pyocd flash {trim_path.name}\n' + '\n'.join(log))
    print(f'flash {which}: rc {r.returncode} after {attempt} attempt(s)')
    if r.returncode:
        sys.exit('flash failed')
    time.sleep(10)


def show(name):
    return session(name, [hello(), ('RUN _radioshow #1', 1.5), ('STATUS', 1.0)])


def must(text, pattern):
    if not re.search(pattern, text):
        print(f'FAIL: expected /{pattern}/')
        return False
    print(f'ok: /{pattern}/')
    return True


def start():
    """Known-good starting image; settings do not matter here, so mbdeploy (which may
    mass-erase) is fine."""
    counter[0] += 1
    attempt = 0
    while attempt < 4:
        attempt += 1
        r = subprocess.run(['uv', 'run', 'mbdeploy', 'deploy', ROBOT, '--hex', str(HEX['a'])],
                           cwd=MBTOOLS, capture_output=True, text=True)
        if r.returncode == 0:
            break
        time.sleep(5)
    text = '\n'.join(l for l in (r.stdout + r.stderr).splitlines() if not l.startswith('['))
    (OUT / f'{counter[0]:02d}-flash_a_start.txt').write_text(f'# mbdeploy {HEX["a"].name} attempt {attempt} rc {r.returncode}\n{text}\n')
    print(f'start flash: rc {r.returncode} after {attempt} attempt(s)')
    if r.returncode:
        sys.exit('start flash failed')
    time.sleep(10)


def baseline():
    must(show('baseline'), r'"source":"name".*"stored":0|"stored":0.*"source":"name"')


def invalid():
    t = session('invalid_sets', [hello(),
                                 ('RUN _radioset 84 29 #1', 1.0), ('RUN _radioset 77 256 #2', 1.0),
                                 ('RUN _radioset 77 1.5 #3', 1.0), ('RUN _radioset -1 29 #4', 1.0),
                                 ('RUN _radioset 77.5 29 #5', 1.0)])
    print('ok: 5 radiostore.fail' if t.count('radiostore.fail') == 5 else 'FAIL: want 5 radiostore.fail')
    must(show('invalid_then_show'), r'"stored":0')


def set_reboot():
    t = session('set_then_reboot', [
        hello(), ('RUN _radioshow #1', 1.5), (f'RUN _radioset {CHANNEL} {GROUP} #2', 1.5), ('STATUS', 1.0),
        ('RUN _radioshow #3', 1.5), ('RUN _reboot #4', 8.0),
        hello(), ('RUN _radioshow #1', 1.5), ('STATUS', 1.0)], tail=2)
    must(t, rf'"ch":{CHANNEL},"grp":{GROUP},"stored":1,"source":"name"')
    must(t, r'reboot\.ok')
    must(t, rf'boot radio tovez ch {CHANNEL} grp {GROUP} stored')
    must(t, rf'"ch":{CHANNEL},"grp":{GROUP},"stored":1,"source":"stored"')
    must(t, rf'channel={CHANNEL} group={GROUP}')


def flash_b():
    flash('b')
    t = session('b_boot_and_show', [('', 4.0), hello(), ('RUN hello #1', 1.0), ('RUN _radioshow #2', 1.5), ('STATUS', 1.0)], reset=True)
    must(t, 'program=b')
    must(t, 'RADIOSTORE:hello')
    must(t, rf'boot radio tovez ch {CHANNEL} grp {GROUP} stored')
    must(t, rf'channel={CHANNEL} group={GROUP}')


def flash_a():
    flash('a')
    t = session('a_boot_and_show', [('', 4.0), hello(), ('RUN _radioshow #1', 1.5), ('STATUS', 1.0)], reset=True)
    must(t, 'program=a')
    must(t, rf'boot radio tovez ch {CHANNEL} grp {GROUP} stored')
    must(t, rf'channel={CHANNEL} group={GROUP}')


def busy():
    t = session('reboot_fail_while_program_runs',
                [hello(), ('RUN pressa #1', 1.0), ('RUN pressb #2', 1.0), ('STATUS', 0.5),
                 ('RUN _reboot #3', 1.5), ('STATUS', 0.5)], tail=1)
    must(t, r'reboot\.fail')
    print('ok: no reboot.ok' if 'reboot.ok' not in t else 'FAIL: reboot.ok seen')
    time.sleep(8)


def queued():
    session('reboot_queued_behind_run_program',
            [hello(), ('RUN pause #1', 0.5), ('RUN _reboot #2', 14.0), hello(), ('STATUS', 1.0)], tail=1)


def clear():
    t = session('clear_then_reboot', [
        hello(), ('RUN _radioclear #1', 1.5), ('RUN _radioshow #2', 1.5), ('RUN _reboot #3', 8.0),
        hello(), ('RUN _radioshow #1', 1.5), ('STATUS', 1.0)], tail=2)
    must(t, r'"stored":0,"source":"stored"')
    must(t, r'reboot\.ok')
    must(t, r'boot radio tovez ch 48 grp 29 name')
    must(t, r'"stored":0,"source":"name"')
    must(t, r'channel=48 group=29')


def moveboot():
    session('reboot_during_raw_move', [
        hello(), ('STATUS', 0.5), ('MOVE_X 300 0 120 15000 #1', 0.4), ('STATUS', 0.3),
        ('RUN _reboot #2', 0.3), ('STATUS', 0.3), ('STATUS', 0.5), ('STATUS', 2.0), ('STATUS', 4.0),
        hello(), ('STATUS', 1.0)], tail=2)


STEPS = [start, baseline, invalid, set_reboot, flash_b, flash_a, busy, queued, moveboot, clear]

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    fns = {f.__name__: f for f in STEPS + [moveboot, queued]}
    fns['all'] = lambda: [f() for f in STEPS]
    fns[which]()
