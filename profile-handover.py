#!/usr/bin/env python3
"""Reserve a separate three-host POWDER topology; start no network software."""
import geni.portal as portal
import geni.rspec.pg as rspec
import geni.rspec.igext as IG

pc = portal.context
pc.defineParameter('core_type', 'Core node hardware type', portal.ParameterType.NODETYPE, 'd430')
pc.defineParameter('cell_type', 'Radio node hardware type', portal.ParameterType.NODETYPE, 'd740')
params = pc.bindParameters()
pc.verifyParameters()
request = pc.makeRequestRSpec()
lan = request.LAN('mobility-lan')
for name, address, hardware in (
    ('core', '10.10.1.1', params.core_type),
    ('source', '10.10.1.11', params.cell_type),
    ('target', '10.10.1.12', params.cell_type),
):
    node = request.RawPC(name)
    node.hardware_type = hardware
    node.disk_image = 'urn:publicid:IDN+emulab.net+image+emulab-ops:UBUNTU22-64-STD'
    interface = node.addInterface('if0')
    interface.addAddress(rspec.IPv4Address(address, '255.255.255.192'))
    lan.addInterface(interface)

tour = IG.Tour()
tour.Description(IG.Tour.TEXT,
    'Preparation-only N2 handover reservation: one core, two radio hosts, and '
    'one shared UE on the source host. No Docker, RAN, core, RIC or traffic '
    'process is installed or started automatically.')
tour.Instructions(IG.Tour.TEXT,
    'Follow experiments/n2-handover/README.md. Verify radio/core compatibility '
    'before manual setup. The target RFsim IQ connection crosses the LAN; '
    'these results must be kept separate from the isolated-cell baseline.')
request.addTour(tour)
pc.printRequestRSpec()
