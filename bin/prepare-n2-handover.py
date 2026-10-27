#!/usr/bin/env python3
"""Prepare an unvalidated two-gNB/one-UE N2 experiment without launching anything."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = '70508ebaf52f2aae420566d380c6537f2efb9f0c'
REQUIRED = {'core_lan_ip', 'source_lan_ip', 'target_lan_ip', 'amf_ip', 'imsi', 'gnb_image', 'ue_image'}
CELLS = (
    {'role': 'source', 'index': 1, 'gnb_id': 3584, 'cell_id': 12345678,
     'pci': 0, 'ssb': 641280, 'point_a': 640008, 'bitmap': 1},
    {'role': 'target', 'index': 2, 'gnb_id': 3585, 'cell_id': 12345679,
     'pci': 1, 'ssb': 621312, 'point_a': 620040, 'bitmap': 2},
)


def validate(topology):
    if set(topology) != REQUIRED:
        raise ValueError('topology must contain exactly: ' + ', '.join(sorted(REQUIRED)))
    for name in ('core_lan_ip', 'source_lan_ip', 'target_lan_ip', 'amf_ip'):
        address = ipaddress.IPv4Address(topology[name])
        if address.is_loopback or address.is_unspecified or address.is_multicast or not address.is_private:
            raise ValueError(f'{name} must be a usable private IPv4 address')
    lan = ipaddress.IPv4Network(topology['core_lan_ip'] + '/26', strict=False)
    for key in ('core_lan_ip', 'source_lan_ip', 'target_lan_ip'):
        address = ipaddress.IPv4Address(topology[key])
        if address not in lan or address in (lan.network_address, lan.broadcast_address):
            raise ValueError('core/source/target must be usable addresses in the same /26 LAN')
    addresses = [topology[key] for key in ('core_lan_ip', 'source_lan_ip', 'target_lan_ip', 'amf_ip')]
    if len(set(addresses)) != len(addresses):
        raise ValueError('core, source, target, and AMF addresses must be distinct')
    if not re.fullmatch(r'[0-9]{15}', topology['imsi']):
        raise ValueError('imsi must contain exactly 15 digits')
    if not topology['imsi'].startswith('20899'):
        raise ValueError('this prototype uses PLMN 208/99; IMSI must match')
    for key in ('gnb_image', 'ue_image'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/:@-]*', topology[key]):
            raise ValueError(f'invalid {key}')
        if '@' in topology[key] and not re.fullmatch(r'[^@]+@sha256:[0-9a-f]{64}', topology[key]):
            raise ValueError(f'{key} digest must use sha256 with 64 lowercase hex digits')
    return topology


def neighbors():
    entries = []
    for serving, peer in ((CELLS[0], CELLS[1]), (CELLS[1], CELLS[0])):
        entries.append(f'''  {{
    nr_cellid = {serving['cell_id']}L;
    neighbour_cell_configuration = (
      {{
        gNB_ID = {peer['gnb_id']};
        nr_cellid = {peer['cell_id']}L;
        physical_cellId = {peer['pci']};
        absoluteFrequencySSB = {peer['ssb']};
        subcarrierSpacing = 1;
        band = 78;
        plmn = {{ mcc = 208; mnc = 99; mnc_length = 2; }};
        tracking_area_code = 1;
      }}
    );
  }}''')
    return 'neighbour_list = (\n' + ',\n'.join(entries) + '''
);
nr_measurement_configuration = {
  Periodical = { enable = 0; includeBeamMeasurements = 0; maxNrofRS_IndexesToReport = 4; };
  A2 = { enable = 0; threshold = 60; time_to_trigger = 1; };
  A3 = ({ physCellId = -1; offset = 10; hysteresis = 0; time_to_trigger = 1; });
};
'''


def render_gnb(topology, cell):
    text = (ROOT / 'etc/gnb-cell.conf.tmpl').read_text()
    values = {'CELL_IDX': cell['index'], 'GNB_ID': cell['gnb_id'], 'PCI': cell['pci'],
              'NR_CELL_ID': cell['cell_id'], 'AMF_IP': topology['amf_ip'],
              'RIC_IP': topology['core_lan_ip'], 'CELL_LAN_IP': topology[cell['role'] + '_lan_ip']}
    for name, value in values.items():
        text = text.replace('@' + name + '@', str(value))
    text = text.replace('nr_cellid = ' + str(cell['cell_id']) + 'L',
                        'nr_cellid = ' + str(cell['cell_id']) + 'L;\n    @include "neighbours.conf"')
    text = re.sub(r'(min_rxtxtime\s*=\s*)3;', r'\g<1>6;', text)
    for key, value in (('absoluteFrequencySSB', cell['ssb']),
                       ('dl_absoluteFrequencyPointA', cell['point_a']),
                       ('ssb_PositionsInBurst_Bitmap', cell['bitmap'])):
        text = re.sub(r'(\b' + key + r'\s*=\s*)[0-9]+;', lambda m: m[1] + str(value) + ';', text)
    text = text.replace('serveraddr = "server";', f'serveraddr = "{topology["source_lan_ip"]}";')
    text = text.replace('options = ("chanmod");', 'options = ();')
    text = text.replace('@include "channelmod_rfsimu.conf"', '')
    if re.search(r'@[A-Z_]+@', text):
        raise ValueError('unresolved gNB template tokens')
    return text


def service(image, name, config, destination, options):
    return {'image': image, 'container_name': name, 'network_mode': 'host',
            'profiles': ['manual-handover'], 'cap_drop': ['ALL'],
            'environment': {'TZ': 'UTC', 'ASAN_OPTIONS': 'detect_leaks=0',
                            'USE_ADDITIONAL_OPTIONS': options},
            'volumes': [{'type': 'bind', 'source': './' + config,
                         'target': destination, 'read_only': True}]}


def generate(topology, output):
    validate(topology)
    if output.exists():
        raise ValueError('output directory already exists; choose a new path')
    files = {}
    for cell in CELLS:
        role = cell['role']
        files[role + '/gnb.conf'] = render_gnb(topology, cell)
        files[role + '/neighbours.conf'] = neighbors()
        gnb = service(topology['gnb_image'], 'ric5g-gnb-cell' + str(cell['index']), 'gnb.conf',
                      '/opt/oai-gnb/etc/gnb.conf',
                      '-E --rfsim --telnetsrv --telnetsrv.shrmod ci '
                      '--telnetsrv.listenaddr 127.0.0.1 --gNBs.[0].min_rxtxtime 6')
        gnb['volumes'].append({'type': 'bind', 'source': './neighbours.conf',
                               'target': '/opt/oai-gnb/etc/neighbours.conf', 'read_only': True})
        services = {'gnb-' + role: gnb}
        if role == 'source':
            ue = (ROOT / 'etc/nr-ue.conf.tmpl').read_text()
            ue = ue[:ue.index('# The rfsimulator')] + '''# This UE serves both gNB RFsim clients. No channel emulation in this stage.
rfsimulator = ({ serveraddr = "server"; serverport = 4043; options = (); });
'''
            files['source/ue.conf'] = ue.replace('@IMSI@', topology['imsi'])
            mobile = service(topology['ue_image'], 'ric5g-ue-cell1-1', 'ue.conf',
                             '/opt/oai-nr-ue/etc/nr-ue.conf',
                             '-E --rfsim -r 106 --numerology 1 --band 78 '
                             f'--uicc0.imsi {topology["imsi"]} -C 3619200000')
            mobile.update(cap_add=['NET_ADMIN', 'NET_RAW'], devices=['/dev/net/tun:/dev/net/tun'])
            mobile['volumes'].extend([
                {'type': 'bind', 'source': '/local/repository/bin/mgen', 'target': '/usr/bin/mgen',
                 'read_only': True, 'bind': {'create_host_path': False}},
                {'type': 'bind', 'source': '/local/logs/mgen', 'target': '/logs/mgen',
                 'bind': {'create_host_path': False}},
            ])
            services['ue'] = mobile
        files[role + '/compose.json'] = json.dumps({'name': 'n2-handover-' + role,
                                                    'services': services}, indent=2) + '\n'
    hashes = {name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()}
    manifest = {'status': 'prepared_not_deployed', 'compatibility': 'unverified',
                'reference_revision': REFERENCE,
                'input_templates_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                           for name in ('etc/gnb-cell.conf.tmpl', 'etc/nr-ue.conf.tmpl')},
                'topology': topology, 'cells': CELLS,
                'instantiated_ues': 1, 'ue_host': 'source', 'rfsim_server': topology['source_lan_ip'],
                'rfsim_port': 4043, 'channel_emulation': False, 'trigger': 'manual_n2',
                'cross_host_iq': True, 'files_sha256': hashes,
                'required_checks': [
                    'Record running radio image IDs, digests, source revisions and patch sets',
                    'Confirm radio builds implement CI trigger_n2_ho and UE mobility reconfiguration',
                    'Confirm AMF/SMF/UPF versions support the complete N2 procedure',
                    'Verify one subscriber, matching PLMN/slice, and independent attachment to each gNB',
                    'Verify neighbor parsing, SSB placement, inter-frequency access and RFsim transport',
                    'Measure radio progression and cross-host IQ transport before comparing delays',
                ],
                'startup_order': ['source gNB', 'shared UE', 'verify source attachment',
                                  'target gNB', 'verify both core registrations',
                                  'start bounded traffic with explicit drain', 'manual handover'],
                'completion_evidence': ['NGAP HandoverRequired/Request/Acknowledge/Command/Notify',
                                        'Target RRC completion and source context release',
                                        'Same UE/PDU session and continuing UL/DL traffic',
                                        'Packet sequence, interruption and lifecycle evidence']}
    files['manifest.json'] = json.dumps(manifest, indent=2) + '\n'
    output.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topology', type=Path, default=ROOT / 'experiments/n2-handover/topology.json')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; never overwritten')
    args = parser.parse_args()
    try:
        result = generate(json.loads(args.topology.read_text()), args.output)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f'ERROR: {exc}\n')
    print(json.dumps({'output': str(args.output.resolve()), 'status': result['status'],
                      'compatibility': result['compatibility'], 'instantiated_ues': 1}, indent=2))


if __name__ == '__main__':
    main()
