import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'bin' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REPORT = load('observation', 'mgen-observation-report.py')
MONITOR = load('resources', 'monitor-cell-resources.py')


@pytest.mark.parametrize('settings', [
    {},
    {'MGEN_DRAIN_SECONDS': '15', 'MGEN_EXPECTED_MAX_DELAY_SECONDS': '381'},
    {'MGEN_DRAIN_SECONDS': '600', 'MGEN_EXPECTED_MAX_DELAY_SECONDS': '381', 'MGEN_COUNT_WAIT_SECONDS': '1'},
    {'MGEN_DRAIN_SECONDS': '600', 'MGEN_EXPECTED_MAX_DELAY_SECONDS': '0'},
    {'MGEN_DRAIN_SECONDS': 'oops', 'MGEN_EXPECTED_MAX_DELAY_SECONDS': '381'},
])
def test_campaign_rejects_inadequate_policy_before_ssh(settings):
    env = {key: value for key, value in os.environ.items() if not key.startswith('MGEN_')}
    result = subprocess.run(['bash', str(ROOT / 'bin/mgen-run-distributed.sh'),
                             'unused-core', 'unused-cell', '1', '1', 'campaign'],
                            env=dict(env, **settings), capture_output=True, text=True)
    assert result.returncode == 2
    assert 'ERROR' in result.stderr or 'WARNING' in result.stderr
    assert 'ssh:' not in result.stderr


@pytest.mark.parametrize('mode, settings, wait', [
    ('full', {'MGEN_COUNT_WAIT_SECONDS': '1'}, '1'),
    ('campaign', {'MGEN_EXPECTED_MAX_DELAY_SECONDS': '381'}, '600'),
])
def test_count_policy_is_forwarded_to_remote_helpers(tmp_path, mode, settings, wait):
    ssh = tmp_path / 'ssh'
    ssh.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
 *send-ul*) echo 'UE_IP=12.1.1.2 TX_DELTA=100' ;;
 *count-ul*) echo UL_RECV=100 ;;
 *listen-dl*) echo UE_IP=12.1.1.2 ;;
 *count-dl*) echo 'DL_RECV=100 RX_DELTA=100' ;;
esac
''')
    sleeper = tmp_path / 'sleep'
    sleeper.write_text('#!/bin/bash\necho "sleep $*" >> "$CALLS"\n')
    ssh.chmod(0o755)
    sleeper.chmod(0o755)
    calls = tmp_path / 'calls'
    subprocess.run(['bash', str(ROOT / 'bin/mgen-run-distributed.sh'), 'core', 'cell', '1', '1', mode],
                   env=dict(os.environ, PATH=f'{tmp_path}:' + os.environ['PATH'],
                            CALLS=str(calls), MGEN_DRAIN_SECONDS='600', **settings),
                   capture_output=True, text=True, check=True)
    lines = calls.read_text().splitlines()
    assert sum(line == f'sleep {wait}' for line in lines) == 2
    if mode == 'full':
        assert not any(line == 'sleep 600' for line in lines)
    assert sum('receiver-status' in line for line in lines) == 4
    assert any('MGEN_DRAIN_SECONDS=600' in line and 'listen-ul' in line for line in lines)


def lifecycle(path, role, start, stop, rc=124):
    Path(str(path) + '.lifecycle.tsv').write_text(
        f'start\tUTC\t{start}\t{role}\t-\t123\nstop\tUTC\t{stop}\t{role}\t{rc}\n')


def test_reconciliation_preserves_censoring_and_requires_clock_evidence(tmp_path):
    tx, rx = tmp_path / 'tx.log', tmp_path / 'rx.log'
    tx.write_text('10 SEND flow>1 seq>1\n11 SEND flow>1 seq>2\n')
    rx.write_text('12 RECV flow>1 seq>1\n')
    lifecycle(tx, 'tx', 100, 110)
    lifecycle(rx, 'rx', 99, 711)
    result = REPORT.report(tx, rx, 600)
    assert result['process_window_status'] == 'clock_alignment_unverified'
    result = REPORT.report(tx, rx, 600, True)
    assert result['process_window_status'] == 'bounded_process_window_observed'
    assert result['unobserved_at_receiver_stop'] == 1
    assert result['last_send_event_raw'] == '11 SEND flow>1 seq>2'
    lifecycle(rx, 'rx', 99, 120)
    assert REPORT.report(tx, rx, 600, True)['process_window_status'] == 'insufficient_drain'
    lifecycle(rx, 'rx', 99, 711, 1)
    assert REPORT.report(tx, rx, 600, True)['process_window_status'] == 'process_failure'


def test_cpu_accounting_excludes_idle_and_iowait():
    assert MONITOR.cpu_usage({'cpu0': [0]*8}, {'cpu0': [20, 0, 10, 60, 10, 0, 0, 0]}) == {'cpu0': 30}
    assert MONITOR.cpu_usage({'cpu0': [0]*8}, {'cpu0': [0]*8}) == {'cpu0': None}


def test_monitor_records_stats_failures_and_bounded_log_tail(tmp_path, monkeypatch):
    log = tmp_path / 'radio.log'
    log.write_text('x' * 70000 + '\nFrame 10 slot 2\n')
    def fail(*args):
        raise OSError('stats unavailable')
    monkeypatch.setattr(MONITOR, 'command', fail)
    monkeypatch.setattr(MONITOR, 'memory', lambda: {'MemAvailable_bytes': 123})
    result = MONITOR.sample(['ric5g-gnb-cell1'], log)
    assert result['container_stats'] == []
    assert result['errors']
    assert result['radio_progress_lines'] == ['Frame 10 slot 2']


def test_real_process_lifecycle_and_late_event(tmp_path):
    # Exercise actual process lifetimes locally. If GNU timeout is unavailable,
    # use a test-only Python timeout adapter, not a container or radio simulation.
    env = dict(os.environ)
    if not shutil.which('timeout'):
        adapter = tmp_path / 'timeout'
        adapter.write_text(f'''#!{sys.executable}
import subprocess, sys
args = sys.argv[1:]
if args[0].startswith('--kill-after='):
    args.pop(0)
limit = float(args.pop(0))
with subprocess.Popen(args) as child:
    try:
        sys.exit(child.wait(timeout=limit))
    except subprocess.TimeoutExpired:
        child.terminate()
        child.wait(timeout=5)
        sys.exit(124)
''')
        adapter.chmod(0o755)
        env['PATH'] = f'{tmp_path}:' + env['PATH']
    executable = tmp_path / 'traffic'
    executable.write_text(f'''#!{sys.executable}
from pathlib import Path
import sys, time
cfg = Path(sys.argv[sys.argv.index('input') + 1])
log = Path(sys.argv[sys.argv.index('output') + 1])
if cfg.read_text() == 'tx':
    log.write_text(str(time.time()) + ' SEND flow>1 seq>1\\n')
else:
    time.sleep(0.8)
    log.write_text(str(time.time()) + ' RECV flow>1 seq>1\\n')
    time.sleep(10)
''')
    executable.chmod(0o755)
    cfg, tx, rx = tmp_path / 'tx.mgn', tmp_path / 'tx.log', tmp_path / 'rx.log'
    cfg.write_text('tx')
    rxcfg = tmp_path / 'rx.mgn'
    rxcfg.write_text('rx')
    shell = 'source "$1"; mgen_observe "$2" "$3" "$4" "$5" "$6"'
    def launch(role, limit, config, log):
        return subprocess.Popen(['bash', '-c', shell, '_', str(ROOT / 'bin/mgen-lifecycle.sh'),
                                 role, str(limit), str(config), str(log), str(executable)], env=env)
    receiver = launch('rx', 2, rxcfg, rx)
    try:
        deadline = time.monotonic() + 3
        while not Path(str(rx) + '.lifecycle.tsv').exists():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        sender = launch('tx', 2, cfg, tx)
        assert sender.wait(timeout=5) == 0
        sender_stopped = time.monotonic()
        assert receiver.poll() is None
        assert receiver.wait(timeout=6) == 0
        assert time.monotonic() - sender_stopped > 1
        assert float(rx.read_text().split()[0]) > float(tx.read_text().split()[0]) + 0.5
        assert REPORT.lifecycle(rx)['stop']['exit_code'] == '124'
    finally:
        if receiver.poll() is None:
            receiver.terminate()
            receiver.wait(timeout=5)
