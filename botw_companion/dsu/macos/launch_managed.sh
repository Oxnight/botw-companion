#!/bin/zsh
set -u

readonly BINARY="$1"
readonly PARENT_PID="$2"
shift 2
readonly EXTRA_ARGS=("$@")
child_pid=""

cleanup() {
  trap - EXIT INT TERM HUP
  if [[ -n "$child_pid" ]] && /bin/kill -0 "$child_pid" 2>/dev/null; then
    /bin/kill -TERM "$child_pid" 2>/dev/null || true
    for _attempt in {1..30}; do
      /bin/kill -0 "$child_pid" 2>/dev/null || break
      /bin/sleep 0.1
    done
    /bin/kill -KILL "$child_pid" 2>/dev/null || true
  fi
  [[ -n "$child_pid" ]] && wait "$child_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM HUP

if [[ "$(/usr/bin/uname -m)" != "arm64" ]]; then
  print -u2 -- "BOTW Companion nécessite un Mac Apple Silicon."
  exit 1
fi
if [[ ! -x "$BINARY" ]]; then
  print -u2 -- "Le moteur JoyConDSU intégré est absent ou non exécutable."
  exit 1
fi

if [[ "${EXTRA_ARGS[1]:-}" == "--list-controllers" ]]; then
  exec "$BINARY" "${EXTRA_ARGS[@]}"
fi

"$BINARY" "${EXTRA_ARGS[@]}" &
child_pid=$!

while /bin/kill -0 "$child_pid" 2>/dev/null; do
  if ! /bin/kill -0 "$PARENT_PID" 2>/dev/null; then
    exit 0
  fi
  /bin/sleep 1
done

wait "$child_pid"
status=$?
child_pid=""
exit $status
