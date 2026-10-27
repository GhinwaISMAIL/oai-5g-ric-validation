# Candidate compatibility assessment — 27 October 2026

The existing custom radio images are a matched candidate pair for the first N2
experiment. They are not yet validated end to end with the core. No new radio
build or core upgrade was selected, and no POWDER system was accessed.

## Radio evidence

| Check | Observed result | What it establishes |
| --- | --- | --- |
| Source version embedded in both executables | `70508ebaf5`, develop, 10 July 2026 | Both report the revision pinned for the existing FlexRIC source checkout |
| GitHub revision resolution | `70508ebaf52f2aae420566d380c6537f2efb9f0c` | The embedded prefix resolves to that full upstream commit |
| Build attestations | Both reference the same `ran-build` and `ran-base` digests | Shared build inputs; no source commit or local patch set is attested |
| RFsim library | Identical SHA-256 in both images | The inspected RFsim library bytes match |
| gNB CI library | `libtelnetsrv_ci.so` contains `trigger_n2_ho` | The manual command marker is compiled in; command execution is untested |
| gNB/UE binaries | Mobility reconfiguration markers present | Relevant code is included; successful execution is untested |
| Main executable dependency loader | All listed dependencies resolved in each container | The main executables' linked dependencies resolve; not a check of every dynamically loaded module |
| Help probes | Both printed help; gNB exit 255, UE exit 0 | Executables launch far enough to parse help under local AMD64 emulation |

The gNB help exit is accompanied by the configuration parser's `exit_fun` message;
it is not a successful handover or a generic runtime-failure classification.
Static string matches do not prove that a procedure executes or is correct.
Embedded build versions are self-reported and do not establish an unmodified tree.
No full source tree is included at `/oai-ran` or `/opt/oai-src` in either image.

The prototype now pins these exact Linux AMD64 registry artifacts:

- gNB: `ghinwa555/oai-gnb-e2-chan@sha256:1bc3c341b498fdc2096721bd0b86f5bdd3ca985a930617163c611db5a9bc5501`
- UE: `ghinwa555/oai-nr-ue-chan@sha256:f00af9714f0e953c79d8e4def6b71d15d9af2c504bca1e0a8db2edbb59d6fb60`

These are artifacts resolved from the registry tags during this assessment, not
proof that an existing reservation runs the same bytes. Compare running container
image identities separately. The images use an Ubuntu 24.04 base; this is distinct
from the host operating-system image and does not establish a compatibility issue.
The existing baseline tags and setup scripts are unchanged.

## Match configuration to the reported source revision

The prototype reference now uses the reported July revision rather than a newer
moving development snapshot. Its [handover tutorial](https://github.com/OPENAIRINTERFACE/openairinterface5g/blob/70508ebaf52f2aae420566d380c6537f2efb9f0c/doc/handover-tutorial.md)
has the nested serving-cell neighbor structure and manual N2 command used by the
prototype. This reduces a configuration-version uncertainty. It does not establish
that undocumented image patches preserve the exact upstream behavior.

## Core decision

Keep the existing `v2.0.0` release family as the first core candidate; do not claim
it lacks N2 support. The [AMF source](https://github.com/openairinterface/oai-cn5g-amf/blob/v2.0.0/src/amf-app/amf_n2.cpp)
implements handover preparation/notification handling, and the
[SMF source](https://github.com/openairinterface/oai-cn5g-smf/blob/v2.0.0/src/smf_app/smf_context.cpp)
handles N2 handover preparation and completion states.

The [AMF v2.1.0 release notes](https://github.com/openairinterface/oai-cn5g-amf/blob/v2.1.0/CHANGELOG.md)
include an N2 handover fix. That justifies tracking version-related failure cases,
not assuming every v2.0.0 test will fail or silently upgrading this experiment.
Use the whole compatible core release/configuration set if a later test justifies
a migration; changing only AMF would introduce another interoperability variable.

Current AMF/SMF/UPF registry digests are recorded in `assessment.json`. Only their
registry identities and selected release sources were examined. Core images were
not downloaded, started, or matched byte-for-byte to those sources. UPF tunnel
updates and end-to-end session continuity remain runtime checks. Existing UDR,
UDM, AUSF, subscriber configuration and core deployment are unchanged.

## Reproduce and retain the evidence

See [evidence/2026-10-27/assessment.json](evidence/2026-10-27/assessment.json) for
identities, file hashes, scope and deferred checks. Alongside it are the registry
indexes/attestations, static inspection results, loader/help output, and the two
inspection scripts. No radio configuration was passed to the help probes.

For static inspection of a pinned image, mount the evidence directory read-only
at `/inspection` in a disposable container, override the entrypoint to `python3`,
and run `/inspection/inspect-radio.py gnb` (or `ue`) with `--network none`,
`--read-only`, `--cap-drop ALL` and `--security-opt no-new-privileges`. The helper
only reads candidate files and prints JSON. `help-probe.py` runs bounded `ldd` and
`--help` commands. Do not use these probes as proof of live RAN functionality.

The remaining operational gate is a fresh native-Linux reservation: independent
attachment to each cell, shared-UE RFsim operation, forward/reverse N2 completion,
and PDU-session/packet continuity with explicit receiver observation policy.
Live testing is deferred. No candidate is marked operationally validated.
