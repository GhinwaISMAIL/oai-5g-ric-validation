#!/usr/bin/env bash
# Shared process observation for cell and core MGEN helpers.

mgen_observe() {
    local role=$1 limit=$2 cfg=$3 log=$4 rc=0
    local executable=${5:-/usr/bin/mgen}
    local lifecycle="${log}.lifecycle.tsv"
    # Times bracket the process, not UDP bind readiness or the final SEND event.
    printf 'start\t%s\t%s\t%s\t-\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date +%s)" "$role" "$BASHPID" > "$lifecycle" || return
    if [ "$role" = tx ]; then
        timeout --kill-after=5 "$limit" "$executable" txlog input "$cfg" output "$log" || rc=$?
    else
        timeout --kill-after=5 "$limit" "$executable" input "$cfg" output "$log" || rc=$?
    fi
    printf 'stop\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date +%s)" "$role" "$rc" >> "$lifecycle" || return
    if [ "$role" = tx ] && [ "$rc" -eq 124 ]; then
        echo "ERROR: sender deadline exceeded; traffic schedule completion is unverified: $log" >&2
        return 124
    fi
    [ "$rc" -eq 0 ] || { [ "$role" = rx ] && [ "$rc" -eq 124 ]; }
}

mgen_launch() {
    local container=$1 role=$2 limit=$3 cfg=$4 log=$5 command
    printf -v command '%s\nmgen_observe %q %q %q %q' \
        "$(declare -f mgen_observe)" "$role" "$limit" "$cfg" "$log"
    if [ "$role" = rx ]; then
        docker exec -d "$container" bash -c "$command"
    else
        docker exec "$container" bash -c "$command"
    fi
}

# A process-aliveness check; this does not establish that UDP bind has completed.
mgen_receiver_check() {
    docker exec "$1" bash -c '
        file=$1
        [ -s "$file" ] || { echo RX_STATE=missing; exit 1; }
        if grep -q "^stop" "$file"; then
            echo RX_STATE=stopped
            cat "$file"
            exit 1
        fi
        # Read the last field of the first line without evaluating its contents.
        pid=$(head -n 1 "$file" | cut -f 6)
        [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null || {
            echo RX_STATE=unconfirmed; exit 1;
        }
        echo RX_STATE=active
        cat "$file"
    ' _ "${2}.lifecycle.tsv"
}
