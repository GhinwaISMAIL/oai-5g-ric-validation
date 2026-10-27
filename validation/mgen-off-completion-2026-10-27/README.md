# Bundled MGEN completion evidence

Executed 27 October 2026 using the repository's unchanged MGEN 5.02b binary.

- Binary SHA-256: `26131fb2203d1c9ec8d7a0891094846ac5255de563d72368b36665b4fc0809b7`
- Linux AMD64 Ubuntu 20.04 inside Docker on macOS ARM64, using x86-64 emulation.
- AMD64 image configuration ID: `sha256:c664f8f86ed5a386b0a340d981b8f81714e21a8b9c73f658c4bea56aa179d54a`
- Registry index digest: `ubuntu@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214`
- Container networking: `none`; traffic was confined to container loopback.
- Repository mounted read-only; no POWDER nodes were accessed.

`tests/integration/mgen-off-completion.sh` ran the actual bundled binary through
the existing lifecycle wrapper, with one- and five-second periodic flows at
10 packets/second, 1000 bytes/packet. Each script ends with OFF only.
Both senders exited 0, before their deadlines, logged OFF and STOP, and sent
exactly 10 and 50 unique packets respectively. The receiver received matching
sequence multisets for both flows; no missing or duplicate sequence was hidden
by the counts. Its planned timeout is recorded as 124 in its lifecycle sidecar
and accepted by the receiver wrapper. See `summary.txt` and the raw logs/scripts.

This resolves the narrow OFF-completion compatibility question for this binary
and environment. It does not establish RFsim performance, distributed readiness,
clock alignment, long-delay observation adequacy, or arbitrary replay completion.
Native Linux and POWDER validation remain pending. Do not interpret these timing
results as a throughput benchmark under x86-64 emulation.

## Reproduce

On an isolated Linux host, run from the repository root, choosing a new output
path (the script refuses to reuse a directory):

```bash
bash tests/integration/mgen-off-completion.sh /tmp/mgen-off-results
```

To reproduce with Docker, from the repository root, first create a separate
writable output directory, then run:

```bash
mkdir /tmp/mgen-off-evidence
docker run --rm --platform linux/amd64 --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp \
  --mount "type=bind,src=$PWD,dst=/repo,readonly" \
  --mount type=bind,src=/tmp/mgen-off-evidence,dst=/evidence \
  ubuntu@sha256:8feb4d8ca5354def3d8fce243717141ce31e2c428701f6682bd2fafe15388214 \
  bash /repo/tests/integration/mgen-off-completion.sh /evidence/run
```

No Docker ports are published. The test uses loopback UDP port 5000; run it on
an isolated host or in the disposable container to avoid a local port collision.
