#!/usr/bin/env python3
"""Reconcile one isolated MGEN sender/receiver log pair and lifecycle records."""
import argparse
import json
from pathlib import Path
import re


def packets(path, event):
    identifiers = set()
    last = None
    unparsed = 0
    duplicates = 0
    for line in path.read_text().splitlines():
        if not re.search(r'\b' + event + r'\b', line):
            continue
        last = line
        flow = re.search(r'\bflow>(\d+)', line)
        sequence = re.search(r'\bseq>(\d+)', line)
        if not flow or not sequence:
            unparsed += 1
            continue
        identifier = (int(flow[1]), int(sequence[1]))
        duplicates += identifier in identifiers
        identifiers.add(identifier)
    return identifiers, last, unparsed, duplicates


def lifecycle(log):
    path = Path(str(log) + '.lifecycle.tsv')
    events = {}
    if not path.exists():
        return events
    for line in path.read_text().splitlines():
        fields = line.split('\t')
        if len(fields) >= 5:
            events[fields[0]] = {'utc': fields[1], 'epoch_seconds': int(fields[2]),
                                 'role': fields[3], 'exit_code': fields[4]}
    return events


def report(tx, rx, drain, synchronized=False):
    sent, last_send, tx_unparsed, tx_duplicates = packets(tx, 'SEND')
    received, last_recv, rx_unparsed, rx_duplicates = packets(rx, 'RECV')
    sender, receiver = lifecycle(tx), lifecycle(rx)
    complete = all('start' in item and 'stop' in item for item in (sender, receiver))
    status = 'incomplete_lifecycle'
    conservative_drain = None
    if complete:
        roles_valid = all(item['start']['role'] == role and item['stop']['role'] == role
                          for item, role in ((sender, 'tx'), (receiver, 'rx')))
        if not roles_valid:
            status = 'process_failure'
        elif sender['stop']['exit_code'] == '124':
            status = 'sender_deadline_exceeded'
        elif sender['stop']['exit_code'] != '0' or receiver['stop']['exit_code'] not in ('0', '124'):
            status = 'process_failure'
        elif tx_unparsed or rx_unparsed or tx_duplicates or received - sent or not sent:
            status = 'invalid_or_ambiguous_packet_logs'
        elif not synchronized:
            status = 'clock_alignment_unverified'
        elif receiver['start']['epoch_seconds'] > sender['start']['epoch_seconds']:
            status = 'receiver_started_after_sender'
        else:
            # Lifecycle times have one-second resolution. Sender process stop is
            # a conservative upper bound for its last SEND, not that event's time.
            conservative_drain = receiver['stop']['epoch_seconds'] - sender['stop']['epoch_seconds'] - 1
            status = 'bounded_process_window_observed' if conservative_drain >= drain else 'insufficient_drain'
    unobserved = sent - received
    return {'process_window_status': status, 'clocks_synchronized_declared': synchronized,
            'required_drain_seconds': drain, 'conservative_drain_seconds': conservative_drain,
            'sender_lifecycle': sender, 'receiver_lifecycle': receiver,
            'last_send_event_raw': last_send, 'last_receive_event_raw': last_recv,
            'last_send_timestamp_raw': last_send.split()[0] if last_send else None,
            'last_receive_timestamp_raw': last_recv.split()[0] if last_recv else None,
            'unique_sent': len(sent), 'unique_received_matching_sent': len(sent & received),
            'unobserved_at_receiver_stop': len(unobserved) if complete else None,
            'unobserved_in_supplied_logs': len(unobserved),
            'unobserved_examples': sorted(unobserved)[:20],
            'unexpected_received': len(received - sent), 'duplicate_receives': rx_duplicates,
            'unparsed_packet_events': tx_unparsed + rx_unparsed,
            'interpretation': 'Unobserved packets may be lost or still queued; network loss is not established.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tx', type=Path, required=True)
    parser.add_argument('--rx', type=Path, required=True)
    parser.add_argument('--drain-seconds', type=int, required=True)
    parser.add_argument('--clocks-synchronized', action='store_true',
                        help='Declare verified clock alignment between the hosts')
    args = parser.parse_args()
    if args.drain_seconds < 0:
        parser.error('drain must be nonnegative')
    result = report(args.tx, args.rx, args.drain_seconds, args.clocks_synchronized)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['process_window_status'] == 'bounded_process_window_observed' else 1)


if __name__ == '__main__':
    main()
