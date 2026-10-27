import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import libconf
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('n2_prepare', ROOT / 'bin/prepare-n2-handover.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def topology():
    return json.loads((ROOT / 'experiments/n2-handover/topology.json').read_text())


def load_config(path):
    with path.open() as stream:
        return libconf.load(stream, includedir=str(path.parent))


def test_generated_config_has_one_shared_ue_and_mutual_neighbors(tmp_path):
    output = tmp_path / 'prototype'
    manifest = MODULE.generate(topology(), output)
    source = load_config(output / 'source/gnb.conf')
    target = load_config(output / 'target/gnb.conf')
    ue = load_config(output / 'source/ue.conf')
    a, b = source['gNBs'][0], target['gNBs'][0]
    assert a['gNB_ID'] != b['gNB_ID']
    assert a['nr_cellid'] != b['nr_cellid']
    assert ue['uicc0']['imsi'] == topology()['imsi']
    assert ue['rfsimulator'][0]['serveraddr'] == 'server'
    for config, serving, peer in ((source, a, b), (target, b, a)):
        assert config['rfsimulator'][0]['serveraddr'] == topology()['source_lan_ip']
        assert config['rfsimulator'][0]['options'] == ()
        relation = next(row for row in serving['neighbour_list'] if row['nr_cellid'] == serving['nr_cellid'])
        neighbor = relation['neighbour_cell_configuration'][0]
        radio = peer['servingCellConfigCommon'][0]
        assert neighbor['nr_cellid'] == peer['nr_cellid']
        assert neighbor['gNB_ID'] == peer['gNB_ID']
        assert neighbor['physical_cellId'] == radio['physCellId']
        assert neighbor['absoluteFrequencySSB'] == radio['absoluteFrequencySSB']
        assert neighbor['band'] == 78
        assert neighbor['plmn']['mcc'] == serving['plmn_list'][0]['mcc']
        assert serving['min_rxtxtime'] == 6
        assert radio['dl_carrierBandwidth'] == 106
        assert radio['dl_subcarrierSpacing'] == 1
    assert a['servingCellConfigCommon'][0]['ssb_PositionsInBurst_Bitmap'] == 1
    assert b['servingCellConfigCommon'][0]['ssb_PositionsInBurst_Bitmap'] == 2
    assert a['servingCellConfigCommon'][0]['absoluteFrequencySSB'] != b['servingCellConfigCommon'][0]['absoluteFrequencySSB']
    assert manifest['instantiated_ues'] == 1
    assert manifest['compatibility'] == 'unverified'
    for name, digest in manifest['files_sha256'].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest


def test_compose_host_placement_matches_shared_ue_and_monitor_helpers(tmp_path):
    output = tmp_path / 'prototype'
    MODULE.generate(topology(), output)
    source = json.loads((output / 'source/compose.json').read_text())['services']
    target = json.loads((output / 'target/compose.json').read_text())['services']
    assert set(source) == {'gnb-source', 'ue'}
    assert set(target) == {'gnb-target'}
    assert source['ue']['container_name'] == 'ric5g-ue-cell1-1'
    assert '-C 3619200000' in source['ue']['environment']['USE_ADDITIONAL_OPTIONS']
    assert '--telnetsrv' not in source['ue']['environment']['USE_ADDITIONAL_OPTIONS']
    for item in [*source.values(), *target.values()]:
        assert item['network_mode'] == 'host'
        assert item['profiles'] == ['manual-handover']
        assert 'depends_on' not in item
    for item in (source['gnb-source'], target['gnb-target']):
        assert '--telnetsrv.shrmod ci' in item['environment']['USE_ADDITIONAL_OPTIONS']
        assert '--telnetsrv.listenaddr 127.0.0.1' in item['environment']['USE_ADDITIONAL_OPTIONS']
    binary = next(item for item in source['ue']['volumes'] if item['target'] == '/usr/bin/mgen')
    assert binary['bind']['create_host_path'] is False


@pytest.mark.parametrize('changes', [
    {'target_lan_ip': '10.10.1.11'}, {'target_lan_ip': '127.0.0.1'},
    {'source_lan_ip': '10.10.1.63'}, {'target_lan_ip': '10.10.2.12'},
    {'imsi': '20899'}, {'imsi': '001010000000001'},
    {'gnb_image': 'image; dangerous'}, {'ue_image': 'image@sha256:bad'}, {'unexpected': True},
])
def test_invalid_topology_is_rejected_before_writing(tmp_path, changes):
    output = tmp_path / 'prototype'
    with pytest.raises(ValueError):
        MODULE.generate(dict(topology(), **changes), output)
    assert not output.exists()


def test_preparation_never_runs_external_programs_or_overwrites(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('preparation must not invoke Docker, SSH, or external programs')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    output = tmp_path / 'prototype'
    MODULE.generate(topology(), output)
    snapshot = (output / 'manifest.json').read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        MODULE.generate(topology(), output)
    assert (output / 'manifest.json').read_bytes() == snapshot


def test_default_candidates_match_preserved_inspection_evidence():
    evidence = ROOT / 'experiments/n2-handover/evidence/2026-10-27'
    assessment = json.loads((evidence / 'assessment.json').read_text())
    inputs = topology()
    for role in ('gnb', 'ue'):
        assert inputs[role + '_image'] == assessment['images'][role]
        assert '@sha256:' in inputs[role + '_image']
    assert MODULE.REFERENCE == assessment['source_revision_reported_by_binaries']
    for name, digest in assessment['evidence_files_sha256'].items():
        assert hashlib.sha256((evidence / name).read_bytes()).hexdigest() == digest
    gnb = json.loads((evidence / 'gnb.static.json').read_text())
    ue = json.loads((evidence / 'ue.static.json').read_text())
    def rfsim_hash(data):
        return next(item['sha256'] for item in data['files'] if item['path'].endswith('/librfsimulator.so'))
    assert rfsim_hash(gnb) == rfsim_hash(ue)
    assert assessment['status'] == 'radio_candidate_pair_identified_end_to_end_unverified'
