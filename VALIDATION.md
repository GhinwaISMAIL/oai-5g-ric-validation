# Validation of the experimental profile

This repository preserves the original radio configuration while correcting
receiver timing, generated subscriber QoS, and channel-control documentation.
No deployed experiment or historical dataset is changed by these commits.

## Receiver observation window

Both endpoint helpers accept `MGEN_DRAIN_SECONDS` (default 15), an unsigned
integer in wall-clock seconds. Receivers run for DURATION plus this interval.
For a long-delay experiment, for example:

```bash
sudo env MGEN_DRAIN_SECONDS=600 bash bin/mgen-cell.sh listen-dl RUN 1 2 6102 900
```

The distributed coordinator forwards this variable to both hosts, includes warmup
and sender shutdown margin in receiver lifetime, and waits the drain interval
before counting each direction. Its default preflight takes longer than before.
Choose a drain interval exceeding expected delays and startup skew; 600 seconds is
an example, not a guarantee. Script-based receivers must not include an earlier
IGNORE/exit event that overrides this observation window. Independently managed
workloads must configure their own receiver lifecycle. Record actual sender stop
and receiver stop times. Packets absent at receiver shutdown are censored until
loss is established by separate evidence; do not label them all as network loss.

## QoS

Generated subscribers now match the local SMF profile: 5QI 9, uplink session AMBR
200 Mbps, downlink session AMBR 400 Mbps. The SMF retains local subscription mode.
Existing databases are not migrated by editing the generator. Verify effective
session settings on a fresh validation deployment before comparing measurements.

## Deployment evidence

Run on a cell node with permission to inspect Docker:

```bash
sudo python3 bin/collect-cell-evidence.py > cell-evidence.json
```

This collects container image identity, selected image metadata, resource limits,
one CPU/memory snapshot, and host CPU topology without changing containers.
It excludes container environment variables and Docker credentials.
CPU percentages are instantaneous evidence, not proof of sustained saturation.
Keep the output with the workload, monitoring interval, frame/slot progression,
wall-clock interval, configuration, and measurement logs. Missing source labels
must be resolved from the image builder before interpreting source buffer limits.

## Controlled performance experiments

Use a separate POWDER reservation and results directory. Keep radio bandwidth,
numerology, TDD pattern, channel conditions, host type, and workload fixed.
Instantiate 1, 3, 6, and 12 UE processes in separate runs using `ues_per_cell`;
reducing only traffic-active UEs does not perform this comparison. Repeat runs and
record actual elapsed radio time divided by wall time, throughput, CPU per
container and per core, memory, and queue/backlog behavior.

Then compare no xApp, minimal KPI reporting, and full monitoring with the same
instantiated UEs and offered traffic. Record reporting periods and log sizes.
Monitoring overhead and CPU contention are hypotheses until these comparisons
support them. Keep the current scheduler, threading, buffers, bandwidth, and
image tags unchanged until this baseline is understood. Do not mix these runs
with a previously calibrated KPI dataset.
