#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Ce test nécessite un runner macOS Apple Silicon." >&2
  exit 1
fi

readonly PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly DMG_PATH="${1:-$PROJECT_ROOT/dist/BOTW_Companion_0.40.0-alpha.24_macOS_arm64.dmg}"
readonly TEST_ROOT="${RUNNER_TEMP:-/tmp}/BOTW Companion macOS installation test"
readonly INSTALL_ROOT="$TEST_ROOT/Applications"
readonly DATA_ROOT="$TEST_ROOT/User Data"
readonly HOME_ROOT="$TEST_ROOT/Home"
readonly TEST_PORT=18767
MOUNT_POINT=""
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && /bin/kill -0 "$SERVER_PID" 2>/dev/null; then
    /bin/kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$MOUNT_POINT" ]]; then
    /usr/bin/hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
  fi
}
trap cleanup EXIT

[[ -f "$DMG_PATH" ]] || { echo "DMG introuvable : $DMG_PATH" >&2; exit 1; }
cmake -E remove_directory "$TEST_ROOT"
mkdir -p "$INSTALL_ROOT" "$DATA_ROOT" "$HOME_ROOT"

ATTACH_OUTPUT="$(/usr/bin/hdiutil attach "$DMG_PATH" -nobrowse -readonly)"
MOUNT_POINT="$(printf '%s\n' "$ATTACH_OUTPUT" | /usr/bin/awk -F '\t' '/\/Volumes\//{print $NF; exit}')"
[[ -d "$MOUNT_POINT/BOTW Companion.app" ]] || {
  echo "Le DMG ne contient pas BOTW Companion.app." >&2
  exit 1
}
[[ -L "$MOUNT_POINT/Applications" ]] || {
  echo "Le DMG ne contient pas le raccourci Applications." >&2
  exit 1
}

/usr/bin/ditto "$MOUNT_POINT/BOTW Companion.app" "$INSTALL_ROOT/BOTW Companion.app"
readonly APPLICATION="$INSTALL_ROOT/BOTW Companion.app"
readonly EXECUTABLE="$APPLICATION/Contents/MacOS/BOTW Companion"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APPLICATION"

[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
    "$APPLICATION/Contents/Info.plist")" == "0.40.0" ]] || {
  echo "CFBundleShortVersionString est invalide." >&2
  exit 1
}
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' \
    "$APPLICATION/Contents/Info.plist")" == "24" ]] || {
  echo "CFBundleVersion est invalide." >&2
  exit 1
}

if [[ "$(/usr/bin/lipo -archs "$EXECUTABLE")" != "arm64" ]]; then
  echo "Le lanceur n'est pas exclusivement arm64." >&2
  exit 1
fi
DSU_EXECUTABLE="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/JoyConDSU' -type f -print -quit)"
SDL_LIBRARY="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/libSDL3.0.dylib' -type f -print -quit)"
[[ -n "$DSU_EXECUTABLE" && -n "$SDL_LIBRARY" ]] || {
  echo "Le runtime DSU macOS est incomplet." >&2
  exit 1
}
for binary in "$DSU_EXECUTABLE" "$SDL_LIBRARY"; do
  [[ "$(/usr/bin/lipo -archs "$binary")" == "arm64" ]] || {
    echo "Architecture DSU inattendue : $binary" >&2
    exit 1
  }
done

# Tous les exécutables et bibliothèques doivent être Apple Silicon, signés et
# indépendants de la machine GitHub qui a construit le DMG.
while IFS= read -r -d '' binary; do
  /usr/bin/file "$binary" | /usr/bin/grep -q 'Mach-O' || continue
  [[ "$(/usr/bin/lipo -archs "$binary")" == "arm64" ]] || {
    echo "Binaire non arm64 dans l'application : $binary" >&2
    exit 1
  }
  /usr/bin/codesign --verify --strict --verbose=2 "$binary"
  if { /usr/bin/otool -L "$binary"; /usr/bin/otool -l "$binary"; } | \
      /usr/bin/grep -E '/opt/homebrew|/usr/local|/Users/' >/dev/null; then
    echo "Dépendance propre à la machine de construction : $binary" >&2
    exit 1
  fi
done < <(/usr/bin/find "$APPLICATION" -type f -print0)

/usr/bin/env -i \
  HOME="$HOME_ROOT" \
  PATH="/usr/bin:/bin" \
  BOTW_COMPANION_DATA_DIR="$DATA_ROOT" \
  "$EXECUTABLE" --package-self-test
/usr/bin/env -i \
  HOME="$HOME_ROOT" \
  PATH="/usr/bin:/bin" \
  "$DSU_EXECUTABLE" --list-controllers >/dev/null

/usr/bin/env -i \
  HOME="$HOME_ROOT" \
  PATH="/usr/bin:/bin" \
  BOTW_COMPANION_DATA_DIR="$DATA_ROOT" \
  "$EXECUTABLE" --server --port "$TEST_PORT" --sans-navigateur >"$TEST_ROOT/server.log" 2>&1 &
SERVER_PID=$!

ready=0
for _attempt in {1..120}; do
  if ! /bin/kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Le serveur installé s'est arrêté prématurément." >&2
    exit 1
  fi
  if /usr/bin/curl --noproxy '*' --silent --fail --max-time 1 \
      "http://127.0.0.1:$TEST_PORT/api/version" | \
      /usr/bin/grep -F '"version": "0.40.0a24"' >/dev/null; then
    ready=1
    break
  fi
  /bin/sleep 0.25
done
if [[ "$ready" != "1" ]]; then
  /bin/cat "$TEST_ROOT/server.log" >&2
  echo "Le serveur installé n'a pas répondu dans le délai prévu." >&2
  exit 1
fi

/usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
  "http://127.0.0.1:$TEST_PORT/" | \
  /usr/bin/grep -F '<title>BOTW Companion</title>' >/dev/null
/usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
  -X POST "http://127.0.0.1:$TEST_PORT/api/shutdown" >/dev/null
wait "$SERVER_PID"
SERVER_PID=""

echo "DMG, application, runtime Python, serveur et DSU arm64 validés."
