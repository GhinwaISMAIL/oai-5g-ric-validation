#!/usr/bin/env python3
"""Record bounded Linux host and radio-container resource time series as JSONL."""
import argparse
import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True,
                          timeout=30).stdout.strip()


def cpu_ticks(path=Path('/proc/stat')):
    return {parts[0]: [int(value) for value in parts[1:9]]
            for line in path.read_text().splitlines()
            if (parts := line.split()) and re.fullmatch(r'cpu\d+', parts[0])}


def cpu_usage(before, after):
    usage = {}
    for core in before.keys() & after.keys():
        delta = [b - a for a, b in zip(before[core], after[core])]
        total = sum(delta)
        usage[core] = (100 * (total - delta[3] - delta[4]) / total
                       if total > 0 and min(delta) >= 0 else None)
    return usage


def memory(path=Path('/proc/meminfo')):
    values = {}
    for line in path.read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            values[key + '_bytes'] = int(value.split()[0]) * 1024
    return values


def progress_tail(path):
    if path is None:
        return []
    with path.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 65536))
        if size > 65536:
            stream.readline()
        lines = stream.read(65536).decode(errors='replace').splitlines()
    return [line for line in lines if re.search(r'\b(frame|slot|sfn)\b', line, re.I)][-5:]


def sample(containers, radio_log):
    errors = []
    stats = []
    if containers:
        try:
            output = command('docker', 'stats', '--no-stream', '--format', '{{json .}}', *containers)
            stats = [json.loads(line) for line in output.splitlines()]
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            errors.append(f'container stats: {exc}')
    try:
        progress = progress_tail(radio_log)
    except OSError as exc:
        progress = []
        errors.append(f'radio log: {exc}')
    return {'container_stats': stats, 'host_memory': memory(),
            'radio_progress_lines': progress, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--instantiated-ues', type=int, required=True)
    parser.add_argument('--monitoring', required=True, help='Label including xApp/reporting interval')
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--radio-log', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New JSONL file; never overwritten')
    args = parser.parse_args()
    if (not math.isfinite(args.interval) or args.interval < 2 or
            not math.isfinite(args.duration) or args.duration <= 0 or args.instantiated_ues < 1):
        parser.error('interval must be >= 2 seconds; duration and instantiated UEs must be positive')
    if not Path('/proc/stat').exists():
        parser.error('run this collector on the Linux cell node')
    containers = [name for name in command('docker', 'ps', '--format', '{{.Names}}').splitlines()
                  if name.startswith(('ric5g-gnb-cell', 'ric5g-ue-cell'))]
    # Opening exclusively avoids replacing evidence from an earlier run.
    with args.output.open('x') as output:
        def emit(record):
            output.write(json.dumps(record) + '\n')
            output.flush()
        emit({'event': 'start', 'utc': utc(), 'run_id': args.run_id,
              'instantiated_ues_declared': args.instantiated_ues,
              'monitoring_declared': args.monitoring, 'container_names': containers,
              'interval_seconds': args.interval, 'duration_seconds': args.duration,
              'radio_log': str(args.radio_log) if args.radio_log else None})
        if not containers:
            emit({'event': 'warning', 'message': 'No running radio containers discovered'})
        started = previous_time = time.monotonic()
        previous = cpu_ticks()
        while time.monotonic() - started < args.duration:
            time.sleep(min(args.interval, max(0, args.duration - (time.monotonic() - started))))
            collection_start = time.monotonic()
            record = sample(containers, args.radio_log)
            current = cpu_ticks()
            now = time.monotonic()
            record.update(event='sample', utc=utc(), elapsed_seconds=now - started,
                          cpu_window_seconds=now - previous_time,
                          per_core_busy_percent=cpu_usage(previous, current),
                          collection_seconds=now - collection_start)
            emit(record)
            previous, previous_time = current, now
        emit({'event': 'stop', 'utc': utc(), 'elapsed_seconds': time.monotonic() - started})


if __name__ == '__main__':
    main()
