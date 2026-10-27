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

The distributed coordinator forwards this variable to both hosts and includes
warmup and sender shutdown margin in receiver lifetime. Its `full` preflight
counts after `MGEN_COUNT_WAIT_SECONDS` (default 1), independently of receiver
lifetime. These are provisional connectivity counts, not final loss estimates.
Increasing receiver lifetime does not force a long wait after each preflight UE.
Choose a drain interval exceeding expected delays and startup skew; 600 seconds is
an example, not a guarantee. Script-based receivers must not include an earlier
IGNORE/exit event that overrides this observation window. Independently managed
workloads must configure their own receiver lifecycle. Record actual sender stop
and receiver stop times. Packets absent at receiver shutdown are censored until
loss is established by separate evidence; do not label them all as network loss.

## Explicit campaign policy

`campaign` mode is a sequential, synthetic bidirectional validation run. It does
not orchestrate an existing arbitrary traffic replay. Example from the laptop:

```bash
MGEN_DRAIN_SECONDS=600 MGEN_EXPECTED_MAX_DELAY_SECONDS=381 DURATION=60 \
  bash bin/mgen-run-distributed.sh CORE_SSH CELL_SSH 1 1 campaign
```

Both policy variables must be explicit. The drain must be at least the declared
expected maximum delay, and the expected delay must be positive. Campaign count
wait defaults to the drain and cannot be shorter. Preflight can instead set
`MGEN_COUNT_WAIT_SECONDS=1` with a longer receiver lifetime. A drain shorter than
a declared expected delay produces a warning, and rejects a campaign before SSH.
The declared delay is an operator assumption; no finite interval guarantees all
queued packets arrive. The 70% connectivity threshold is not a KPI acceptance
criterion. Independently driven replay workloads must enforce their own explicit
observation and counting policy; these controls do not automatically cover them.

## Process lifecycle and packet reconciliation

Both helpers use the shared `bin/mgen-lifecycle.sh`; deploy the whole repository
on both nodes. Each sender and receiver writes `<log>.lifecycle.tsv` beside its
packet log, with process start/stop UTC times, epoch seconds, role, and stop exit
code. Sender logs now explicitly enable `txlog`. Start records include the wrapper
PID. Checks before sending and before counting reject missing, stopped, or
unconfirmed receiver processes. They establish process aliveness, not UDP bind
readiness; verify LISTEN/traffic reception on the separate test reservation.

Lifecycle times bracket execution, not the exact final SEND or socket activation.
A detached receiver can still exit after an aliveness check. Inspect its final
stop record after natural shutdown; a missing stop record invalidates lifecycle
validation. Exit code 124 is accepted only for a receiver's planned timeout.
A sender deadline exit (124) fails the helper and is reported as
`sender_deadline_exceeded` by reconciliation. Other nonzero sender exits and
receiver exits other than 124 are process failures. Timeout has a five-second
forced-kill fallback. Unexpected
process/container termination may prevent a stop record from being written.
Use unique run/script names; rerunning a name overwrites that run's artifacts.

The sender rule deliberately fails closed. An OFF event stops a flow; it does not
by itself prove that the intended packet count was sent or that MGEN exited.
A sender that sends its traffic and then idles until its deadline will also fail.
Do not bypass this by treating 124 as success. Before any future exception, verify
the intended schedule, final OFF/SEND events, and exact offered packet counts
against the actual deployed MGEN logs. A clean process exit alone is not proof
that an arbitrary replay schedule completed either. The current tools do not
validate that schedule automatically.

The [MGEN reference](https://github.com/USNavalResearchLaboratory/mgen/blob/master/doc/mgen.html)
describes OFF, SEND, and process STOP as distinct events. Live validation must
check how the bundled binary terminates after the generated OFF-only scripts;
those scripts may now fail until clean completion or schedule evidence is
established. No unchecked timeout exception is provided for synthetic campaigns
or arbitrary script replay.

After receivers stop, collect each isolated sender/receiver pair and both
sidecars onto one machine, then run:

```bash
python3 bin/mgen-observation-report.py --tx TX.log --rx RX.log \
  --drain-seconds 600 --clocks-synchronized > observation.json
```

Declare `--clocks-synchronized` only after verifying host clock alignment; the tool
does not synchronize or measure clock offsets. It reports raw last SEND/RECV
events and timestamps, unique flow/sequence matches, duplicates, unexpected
receives, and unobserved packets. It rejects absent/incomplete lifecycle records,
process failures, ambiguous sender sequences, unparsed events, and an insufficient
process observation interval. It subtracts a second for timestamp resolution and
uses sender process stop as a conservative bound on the last SEND. Timing checks
cannot prove UDP readiness or exclude every intermediate interruption.

One pair must contain only one isolated run/direction with unique sender flow and
sequence identifiers. Events are expected to use MGEN text `SEND`/`RECV`, `flow>`
and `seq>` fields. The report returns nonzero if the bounded process window cannot
be established. Even a passing window does not establish network loss or that
queues drained: unobserved packets are censored, and radio queue occupancy at
shutdown remains unknown without independent RLC evidence. Read the JSON as well
as the exit code. The tool does not certify the historical KPI dataset.

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

## Repeated resource collection

Run the separate lightweight collector on the Linux cell node. The UE count and
monitoring label are operator declarations, recorded alongside discovered radio
container names so mismatches can be investigated:

```bash
sudo python3 bin/monitor-cell-resources.py --run-id scale-12-full \
  --instantiated-ues 12 --monitoring 'full-xapp-10ms' \
  --duration 300 --interval 10 --output scale-12-full.jsonl
```

Optionally supply `--radio-log /path/to/gnb.log` for a bounded tail of lines
mentioning frame, slot, or SFN. The tool does not enable logging or modify the
radio. These are raw log excerpts; they may repeat or be absent, and are not a
computed radio-speed measurement. Record unambiguous frame/slot progression
with wall-clock timestamps separately and account for frame counter wraparound.

JSONL records include UTC and monotonic elapsed time, per-core busy CPU percentage
from `/proc/stat` deltas (excluding idle and iowait), available host memory,
per-container Docker CPU/memory readings, collection time, and errors. Collection
uses a 10-second default interval, permits no interval below two seconds, and
records one Docker stats snapshot per sample. The discovered container set is
fixed for a run; restart the collector after changing instantiated containers.
Missing stats or radio-log access is recorded, not interpreted as zero load.
Output files are created exclusively and never overwritten. Compare monitor-on
and monitor-off runs to assess its own overhead. Collection may extend beyond the
requested duration by bounded command timeouts. Retain start/stop records and
reject interrupted or incomplete evidence as appropriate.

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
