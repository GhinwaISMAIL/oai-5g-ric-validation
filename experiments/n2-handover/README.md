# Two-cell, one-UE N2 handover prototype

Status: configuration preparation only. No successful handover, deployed image
compatibility, or reservation readiness is claimed. Live testing remains deferred.

The first milestone is manual inter-gNB N2 handover through a shared core. The
source and target are distinct full gNBs; this is not intra-CU F1 handover. Exactly
one UE persists throughout the test. Restarting it on another cell is reattachment
and does not establish handover or session continuity.

## Topology and resources

| Reserved host | Experimental IP | Intended processes |
| --- | --- | --- |
| core | 10.10.1.1 | compatible AMF/SMF/UPF and subscriber database; optional RIC |
| source | 10.10.1.11 | source gNB, shared UE acting as RFsim server |
| target | 10.10.1.12 | target gNB acting as another RFsim client |

Use `profile-handover.py` as the POWDER profile entrypoint for a new reservation.
It reserves three raw PCs but installs and starts nothing. Hardware defaults are
one d430 and two d740 nodes; allocation availability is not checked here. Do not
use the existing `profile.py`/`node-setup.sh`/`cell-setup.sh` for this experiment:
those automatically start independent cells and their own UEs. They are unchanged.

Both gNBs connect to the same UE RFsim server on source port 4043. Source IQ is
local; target IQ crosses the experimental LAN. This deliberately changes the
baseline's cell-local IQ assumption. LAN bandwidth, latency, and radio progression
must be measured before attributing performance changes to handover or load.
One UE reduces initial load but does not establish sufficient CPU headroom.
Start without xApps, with low offered traffic and a stable transport.

## Prepare files locally

From the validation repository root:

```bash
python3 bin/prepare-n2-handover.py \
  --topology experiments/n2-handover/topology.json \
  --output /tmp/n2-handover-prepared
```

The generator invokes no Docker, SSH, traffic generator, or network operations.
It writes only a new output directory and refuses to overwrite one. Outputs are
`source/{gnb.conf,ue.conf,neighbours.conf,compose.json}`,
`target/{gnb.conf,neighbours.conf,compose.json}`, and `manifest.json`.
The manifest records topology, identities, content hashes, startup order,
compatibility checks and required completion evidence. Its status remains
`prepared_not_deployed`/`unverified`; generating files cannot satisfy runtime checks.

Compose services have an explicit `manual-handover` profile and no automatic
startup dependencies. Validate their syntax without starting containers:

```bash
docker compose --profile manual-handover -f /tmp/n2-handover-prepared/source/compose.json config --quiet
docker compose --profile manual-handover -f /tmp/n2-handover-prepared/target/compose.json config --quiet
```

The source host has `gnb-source` and `ue`; the target has only `gnb-target`.
Container names match the existing evidence/resource/MGEN helpers: gNB cell1,
gNB cell2, and UE cell1-1. The UE stays physically on source after handover.
Never run this alongside the baseline on the same hosts: host networking,
RFsim ports, GTP ports, container names, and the UE tunnel can conflict.
UE telnet is not enabled, avoiding collision with the source gNB telnet listener.
Each gNB control listener is restricted to loopback on its own host.

## Radio changes specific to the prototype

The generator derives configuration from the existing templates, with these
explicit departures for the initial interoperability test:

- UE is the RFsim server; both gNBs are clients.
- Source/target have PCI 0/1, gNB IDs 3584/3585, and distinct NR cell IDs.
- Neighbor relations describe both cells, keyed by serving NR cell ID, with
  consistent PLMN 208/99, TAC 1 and band 78.
- Source SSB ARFCN is 641280, Point A 640008, initial UE frequency 3619200000 Hz.
  Target SSB ARFCN is 621312, Point A 620040. This is an inter-frequency prototype.
- SSB bitmaps are 1 and 2; `min_rxtxtime` is 6.
- Channel emulation is disabled on all radio processes for this first stage.
  Do not apply `channel-cell.py` or assume the baseline channel-model index mapping
  applies to the shared UE. Channel modeling needs a separate validation stage.
- Band 78, 106 PRBs, 30 kHz SCS, antenna configuration and the TDD pattern are
  retained from the baseline. This is not a calibrated performance comparison.

These choices follow the upstream N2 RFsim example where applicable, adapted to
this project's PLMN and topology. The reference is OAI revision
`70508ebaf52f2aae420566d380c6537f2efb9f0c`, whose handover tutorial blob is
`a92aa2350da3e5441d13c56eedb5ccbad864cb1e`:
[handover tutorial](https://github.com/OPENAIRINTERFACE/openairinterface5g/blob/70508ebaf52f2aae420566d380c6537f2efb9f0c/doc/handover-tutorial.md).
This is a documentation reference, not a claim that the custom images were built
from that revision. The OAI software UE example uses manual triggers; automatic
measurement-driven mobility and RIC-driven control are later milestones.

## Compatibility checks before deployment

The example topology now pins the inspected radio artifacts by registry digest.
Both binaries report revision `70508ebaf5`; the gNB CI library includes the N2
trigger marker and the RFsim libraries match byte for byte. See
[COMPATIBILITY.md](COMPATIBILITY.md) for the measured evidence and limitations.
These are static/help checks, not an operational handover certification. Record
running image identities, source/build metadata and local patches during the
reservation. Do not interpret an embedded version as proof of an unmodified tree.

Confirm all of the following on the selected builds before the complete test:

1. gNB has `telnetsrv`, its CI module, `trigger_n2_ho`, neighbor configuration
   parsing, and the N2 RRC/NGAP procedures. UE supports the required RFsim server
   mode, multiple gNB connections and mobility reconfiguration/retuning.
2. The selected AMF, SMF and UPF complete N2 handover and user-plane switching.
   The currently configured core v2.0.0 is unverified for this procedure; no core
   image upgrade or configuration switch is made by this prototype.
3. Both gNBs register independently with the core and the one UE can attach to
   each cell individually, with the other gNB stopped. Test the target using
   its initial center frequency 3319680000 Hz in a separate attachment check;
   restore 3619200000 Hz for the source-first handover run. Do not register a
   second copy of the UE/IMSI concurrently.
4. One subscriber exists for IMSI 208990100001100, matching the generated UICC
   credentials, PLMN, SST/DNN and effective QoS. Provisioning more subscriber rows
   does not require instantiating more UE processes.

If a build lacks a capability, select or reproducibly build a compatible radio/core
set in this experiment. Do not rebuild or replace baseline images. Resolve those
checks with deployment evidence; local parsing/Compose checks cannot prove them.

## Host preparation and manual startup for the later reservation

Install Docker/Compose on the fresh radio hosts, prepare the chosen compatible
core on its host, and check out this validation repository at `/local/repository`
on all three. The generated source UE bind-mounts `/local/repository/bin/mgen`
and `/local/logs/mgen`; the binary must exist and be executable, and the log
directory must exist and be writable. Missing bind sources are not auto-created.
Preserve binary hashes with the experiment evidence. No installer runs automatically.

Each radio host needs routes to the core's 192.168.71.128/26 and
192.168.72.128/26 networks via 10.10.1.1, with return reachability through the core.
Verify NGAP/SCTP, N3/GTP-U and bidirectional RFsim TCP connectivity. Allow target
to reach source TCP 4043 on the experimental LAN, without exposing telnet there.
Use distinct Docker bridge addresses on hosts if the RIC is enabled, as documented
for the baseline. The generator does not change routes, firewalls or interfaces.

Copy the generated source and target directories to their respective hosts.
The two Compose files intentionally have no dependencies enforcing source-first
attachment. Run each stage separately, using actual logs and the UE tunnel as
progress checks rather than assuming a fixed sleep is enough:

1. Start only `gnb-source` on source. It may retry RFsim until UE is started.
2. Start `ue` on source; verify source attachment, PDU session, assigned UE IP,
   the `oaitun_ue1` tunnel, and actual bidirectional packet reception.
3. Start only `gnb-target` on target. Verify its independent N2 registration and
   RFsim connection, while the UE remains attached to source.
4. Start a low-load, bounded UL/DL test with explicit observation/drain policy.
   Keep sender, receiver, lifecycle, NGAP and RRC evidence throughout handover.

For example, in the directory for the relevant host:

```bash
sudo docker compose --profile manual-handover -f compose.json up -d gnb-source
# After verifying that source has started:
sudo docker compose --profile manual-handover -f compose.json up -d ue
# On target only, after verifying source attachment:
sudo docker compose --profile manual-handover -f compose.json up -d gnb-target
```

Do not start the whole Compose project in one command. If the two-client RFsim
setup blocks, retain logs and stop/restart this experiment's radio processes in
source-first order. The upstream tutorial documents this possible limitation.
Do not restart the baseline or call automatic restarts successful handovers.

## Trigger and acceptance evidence

On source, read the actual UE RRC ID from its RRC state/logs; do not assume it is 1.
After confirming the selected binary's command syntax, the upstream manual request
is `ci trigger_n2_ho <target PCI>,<UE RRC ID>`. For target PCI 1:

```bash
UE_RRC_ID=1  # Replace with the observed source RRC ID.
printf 'ci trigger_n2_ho 1,%s\n' "$UE_RRC_ID" | nc -N -w 3 127.0.0.1 9090
```

A telnet response or successful socket write means only a request was sent.
Accept handover only with the matching source/target/core contexts and all of:

- NGAP preparation/resource allocation, Handover Command and Handover Notify.
- UE target-side RRC completion and eventual source context release.
- Same UE and PDU session with traffic continuing through the target user plane;
  log the UE address before/after and investigate any change or session rebuild.
- SEND/RECV sequence reconciliation, process lifecycle records, bounded interruption
  and explicitly censored packets. Retain packet capture and original timestamps.

For a reverse request, use target's current UE RRC ID and target PCI 0, on the
host now serving the UE. IDs may change. Do not reuse a stale ID by assumption.
Keep the UE and its MGEN endpoint on source; switching the traffic SSH endpoint
to target would select a host without the UE.

Use `collect-cell-evidence.py` and `monitor-cell-resources.py` on both radio hosts.
Declare `--instantiated-ues 1` on source and `--instantiated-ues 0` on target:
the monitor now accepts a zero count for a host with no local UE process.
The experiment still contains one UE total, even after its serving gNB changes.
Use the existing radio-speed measurement alongside it; no automatic speed factor
is provided by this prototype.

## Local verification and remaining work

```bash
python3 -m pip install -r tests/requirements.txt
python3 -m pytest -q
```

Tests parse generated libconfig files including neighbor includes, check peer
identity/frequency consistency, one-UE host placement and container capabilities,
reject invalid topologies, verify artifact hashes, and prohibit launching external
programs during preparation. Compose syntax was checked separately. These checks
do not execute OAI, allocate POWDER hardware, or prove a handover.

Next: establish the compatible image/core set, then perform the three-host
reservation checks above. Only after one reliable forward/reverse handover should
we add UEs, channel impairments, xApps, or automated triggers. Keep all new results
separate from the historical KPI dataset and the isolated-cell validation runs.
