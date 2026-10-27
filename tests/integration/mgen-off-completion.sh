#!/usr/bin/env bash
# Run the exact bundled Linux binary against a loopback-only receiver.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
BINARY=${MGEN_BINARY:-$ROOT/bin/mgen}
[ "$#" -eq 1 ] || { echo "Usage: $0 NEW_RESULTS_DIRECTORY" >&2; exit 2; }
mkdir "$1"
RESULTS=$(cd "$1" && pwd)
source "$ROOT/bin/mgen-lifecycle.sh"
exec > >(tee "$RESULTS/summary.txt") 2>&1
printf 'UTC: '; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'Architecture: '; uname -m
sha256sum "$BINARY"
printf '0.0 LISTEN UDP 5000\n' > "$RESULTS/receiver.mgn"

mgen_observe rx 12 "$RESULTS/receiver.mgn" "$RESULTS/receiver.log" "$BINARY" &
receiver=$!
trap 'kill "$receiver" 2>/dev/null || true; wait "$receiver" 2>/dev/null || true' EXIT
sleep 0.5
for duration in 1 5; do
    flow=$duration
    base="$RESULTS/sender-$duration"
    printf '0.0 ON %s UDP DST 127.0.0.1/5000 PERIODIC [10 1000]\n%s.0 OFF %s\n' \
        "$flow" "$duration" "$flow" > "$base.mgn"
    rc=0
    mgen_observe tx "$((duration + 5))" "$base.mgn" "$base.log" "$BINARY" || rc=$?
    expected=$((duration * 10))
    sent=$(awk '/ SEND / {n++} END {print n+0}' "$base.log")
    unique=$(awk '/ SEND / {for (i=1;i<=NF;i++) if ($i ~ /^seq>/) seen[$i]=1} END {for (s in seen) n++; print n+0}' "$base.log")
    off=$(awk -v flow="flow>$flow" '/ OFF / {for (i=1;i<=NF;i++) if ($i==flow) n++} END {print n+0}' "$base.log")
    stop=$(awk '/ STOP/ {n++} END {print n+0}' "$base.log")
    printf 'duration=%s sender_rc=%s expected=%s sent=%s unique=%s off=%s stop=%s\n' \
        "$duration" "$rc" "$expected" "$sent" "$unique" "$off" "$stop"
    [ "$rc" -eq 0 ] && [ "$sent" -eq "$expected" ] && [ "$unique" -eq "$expected" ] && \
        [ "$off" -eq 1 ] && [ "$stop" -eq 1 ] || exit 1
done
receiver_rc=0
wait "$receiver" || receiver_rc=$?
trap - EXIT
printf 'Receiver wrapper exit: %s\n' "$receiver_rc"
[ "$receiver_rc" -eq 0 ] || exit 1
for duration in 1 5; do
    received=$(awk -v flow="flow>$duration" '/ RECV / {for(i=1;i<=NF;i++) if($i==flow) n++} END {print n+0}' "$RESULTS/receiver.log")
    expected=$((duration * 10))
    printf 'flow=%s expected=%s received=%s\n' "$duration" "$expected" "$received"
    [ "$received" -eq "$expected" ] || exit 1
    # Compare complete sequence multisets: equal counts alone could hide a
    # missing packet offset by a duplicate reception.
    cmp <(awk '/ SEND / {for(i=1;i<=NF;i++) if($i ~ /^seq>/) print $i}' \
        "$RESULTS/sender-$duration.log" | LC_ALL=C sort) \
        <(awk -v flow="flow>$duration" '/ RECV / {f=""; s=""; for(i=1;i<=NF;i++) {if($i==flow) f=$i; if($i ~ /^seq>/) s=$i} if(f!="") print s}' \
        "$RESULTS/receiver.log" | LC_ALL=C sort)
done
printf 'PASS: both OFF-only senders exited cleanly with exact loopback packet counts\n'
