#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
log_directory="${1:-.}"
mkdir -p "$log_directory"

server_pid=""
stop_server() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  server_pid=""
}
trap stop_server EXIT
for browser in webkit chromium firefox; do
  echo "::group::$browser flow"
  python3 tools/browser_test_server.py --port 18765 >"$log_directory/browser-test-$browser.log" 2>&1 &
  server_pid=$!
  ready=0
  for ((attempt = 1; attempt <= 120; attempt++)); do
    if curl --noproxy '*' --silent --fail --max-time 1 \
        http://127.0.0.1:18765/api/version >/dev/null; then
      ready=1
      break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
      cat "$log_directory/browser-test-$browser.log"
      exit 1
    fi
    sleep 0.25
  done
  if [[ "$ready" != "1" ]]; then
    cat "$log_directory/browser-test-$browser.log"
    exit 1
  fi
  BOTW_BROWSER_TEST_TIMEOUT_MS=120000 \
    node tools/browser_smoke.js http://127.0.0.1:18765 "$browser"
  stop_server
  echo "::endgroup::"
done
