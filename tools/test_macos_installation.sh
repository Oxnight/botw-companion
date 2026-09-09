#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Ce test nécessite un runner macOS Apple Silicon." >&2
  exit 1
fi

readonly PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly CURRENT_DMG_NAME="$(python3 "$PROJECT_ROOT/tools/release_metadata.py" --field dmg_name)"
readonly EXPECTED_PEP440="$(python3 "$PROJECT_ROOT/tools/release_metadata.py" --field pep440_version)"
readonly EXPECTED_MACOS_SHORT="$(python3 "$PROJECT_ROOT/tools/release_metadata.py" --field macos_short_version)"
readonly EXPECTED_MACOS_BUNDLE="$(python3 "$PROJECT_ROOT/tools/release_metadata.py" --field macos_bundle_version)"
readonly DMG_PATH="${1:-$PROJECT_ROOT/dist/$CURRENT_DMG_NAME}"
readonly PREVIOUS_DMG_PATH="${2:-}"
readonly TEST_ROOT="${RUNNER_TEMP:-/tmp}/BOTW Companion macOS installation test"
readonly CLEAN_APPLICATION="$TEST_ROOT/Applications clean/BOTW Companion.app"
readonly CLEAN_DATA_ROOT="$TEST_ROOT/Clean user data"
readonly CLEAN_HOME_ROOT="$TEST_ROOT/Clean home"
readonly UPGRADE_APPLICATION="$TEST_ROOT/Applications upgrade/BOTW Companion.app"
readonly UPGRADE_HOME_ROOT="$TEST_ROOT/Upgrade home"
readonly UPGRADE_DATA_ROOT="$UPGRADE_HOME_ROOT/Library/Application Support/BOTW Companion"
MOUNT_POINT=""
SERVER_PID=""

detach_dmg() {
  if [[ -n "$MOUNT_POINT" ]]; then
    /usr/bin/hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
    MOUNT_POINT=""
  fi
}

cleanup() {
  if [[ -n "$SERVER_PID" ]] && /bin/kill -0 "$SERVER_PID" 2>/dev/null; then
    /bin/kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  detach_dmg
}
trap cleanup EXIT

attach_dmg() {
  local dmg_path="$1"
  local attach_output
  attach_output="$(/usr/bin/hdiutil attach "$dmg_path" -nobrowse -readonly)"
  MOUNT_POINT="$(printf '%s\n' "$attach_output" | /usr/bin/awk -F '\t' '/\/Volumes\//{print $NF; exit}')"
  [[ -d "$MOUNT_POINT/BOTW Companion.app" ]] || {
    echo "Le DMG ne contient pas BOTW Companion.app : $dmg_path" >&2
    exit 1
  }
  [[ -L "$MOUNT_POINT/Applications" ]] || {
    echo "Le DMG ne contient pas le raccourci Applications : $dmg_path" >&2
    exit 1
  }
}

copy_application_from_dmg() {
  local dmg_path="$1"
  local destination="$2"
  attach_dmg "$dmg_path"
  mkdir -p "$(dirname "$destination")"
  /usr/bin/ditto "$MOUNT_POINT/BOTW Companion.app" "$destination"
  detach_dmg
}

assert_current_application() {
  local application="$1"
  local executable="$application/Contents/MacOS/BOTW Companion"
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$application"
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$application/Contents/Info.plist")" == \
    "fr.oxnight.botw-companion" ]] || { echo "Identifiant du bundle invalide." >&2; exit 1; }
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$application/Contents/Info.plist")" == \
    "$EXPECTED_MACOS_SHORT" ]] || { echo "CFBundleShortVersionString est invalide." >&2; exit 1; }
  local actual_bundle_version
  actual_bundle_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$application/Contents/Info.plist")"
  [[ "$actual_bundle_version" == "$EXPECTED_MACOS_BUNDLE" ]] || {
    echo "CFBundleVersion est invalide : attendu $EXPECTED_MACOS_BUNDLE, obtenu $actual_bundle_version." >&2
    exit 1
  }
  [[ "$(/usr/bin/lipo -archs "$executable")" == "arm64" ]] || {
    echo "Le lanceur n'est pas exclusivement arm64." >&2
    exit 1
  }

  local dsu_executable sdl_library localization nomenclature
  dsu_executable="$(find "$application" -path '*/botw_companion/dsu/macos/JoyConDSU' -type f -print -quit)"
  sdl_library="$(find "$application" -path '*/botw_companion/dsu/macos/libSDL3.0.dylib' -type f -print -quit)"
  localization="$(find "$application" -path '*/botw_companion/data/localization_fr.json' -type f -print -quit)"
  nomenclature="$(find "$application" -path '*/botw_companion/data/nomenclature_fr_reference.json' -type f -print -quit)"
  [[ -n "$dsu_executable" && -n "$sdl_library" && -n "$localization" && -n "$nomenclature" ]] || {
    echo "Le paquet macOS ne contient pas toutes ses ressources hors ligne." >&2
    exit 1
  }
  for document in LICENSE CHANGELOG.md THIRD_PARTY_NOTICES.md DATA_SOURCES.md PRIVACY.md SECURITY.md \
    licenses/PYTHON-3.12.txt licenses/SDL3-3.4.14.txt; do
    find "$application" -path "*/$document" -type f -print -quit | grep -q . || {
      echo "Document absent de l'application installée : $document" >&2; exit 1;
    }
  done
  for binary in "$dsu_executable" "$sdl_library"; do
    [[ "$(/usr/bin/lipo -archs "$binary")" == "arm64" ]] || {
      echo "Architecture DSU inattendue : $binary" >&2
      exit 1
    }
  done

  while IFS= read -r -d '' binary; do
    /usr/bin/file "$binary" | /usr/bin/grep -q 'Mach-O' || continue
    [[ "$(/usr/bin/lipo -archs "$binary")" == "arm64" ]] || {
      echo "Binaire non arm64 dans l'application : $binary" >&2
      exit 1
    }
    /usr/bin/codesign --verify --strict --verbose=2 "$binary"
    unsafe_metadata="$({
      /usr/bin/otool -L "$binary" | /usr/bin/awk 'NR > 1 { print $1 }'
      /usr/bin/otool -l "$binary" | /usr/bin/awk '
        $1 == "cmd" && $2 == "LC_RPATH" { reading = 1; next }
        reading && $1 == "path" { if (!seen[$2]++) print $2; reading = 0 }
      '
    } | /usr/bin/grep -E '/opt/homebrew|/usr/local|/Users/' || true)"
    if [[ -n "$unsafe_metadata" ]]; then
      echo "Dépendance propre à la machine de construction : $binary" >&2
      printf '%s\n' "$unsafe_metadata" >&2
      exit 1
    fi
  done < <(/usr/bin/find "$application" -type f -print0)
}

run_current_application() {
  local application="$1"
  local home_root="$2"
  local data_root="$3"
  local port="$4"
  local validate_upgrade="$5"
  local executable="$application/Contents/MacOS/BOTW Companion"
  local dsu_executable
  dsu_executable="$(find "$application" -path '*/botw_companion/dsu/macos/JoyConDSU' -type f -print -quit)"
  local -a clean_environment=(/usr/bin/env -i "HOME=$home_root" "PATH=/usr/bin:/bin")
  if [[ -n "$data_root" ]]; then
    clean_environment+=("BOTW_COMPANION_DATA_DIR=$data_root")
  fi

  "${clean_environment[@]}" "$executable" --package-self-test
  /usr/bin/env -i HOME="$home_root" PATH="/usr/bin:/bin" \
    "$dsu_executable" --list-controllers >/dev/null
  "${clean_environment[@]}" "$executable" --server --port "$port" --sans-navigateur \
    >"$TEST_ROOT/server-$port.log" 2>&1 &
  SERVER_PID=$!

  local ready=0 identity_json=""
  for _attempt in {1..120}; do
    if ! /bin/kill -0 "$SERVER_PID" 2>/dev/null; then
      /bin/cat "$TEST_ROOT/server-$port.log" >&2
      echo "Le serveur installé s'est arrêté prématurément." >&2
      exit 1
    fi
    identity_json="$(/usr/bin/curl --noproxy '*' --silent --fail --max-time 1 \
      "http://127.0.0.1:$port/api/version" || true)"
    if printf '%s' "$identity_json" | /usr/bin/grep -F "\"version\": \"$EXPECTED_PEP440\"" >/dev/null; then
      ready=1
      break
    fi
    /bin/sleep 0.25
  done
  [[ "$ready" == "1" ]] || {
    /bin/cat "$TEST_ROOT/server-$port.log" >&2
    echo "Le serveur installé n'a pas répondu dans le délai prévu." >&2
    exit 1
  }

  if [[ "$validate_upgrade" == "yes" ]]; then
    /usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
      "http://127.0.0.1:$port/api/manual" >"$TEST_ROOT/manual.json"
    /usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
      "http://127.0.0.1:$port/api/routes" >"$TEST_ROOT/routes.json"
    /usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
      "http://127.0.0.1:$port/api/preferences" >"$TEST_ROOT/preferences.json"
    python3 - "$TEST_ROOT/manual.json" "$TEST_ROOT/routes.json" "$TEST_ROOT/preferences.json" <<'PY'
import json
from pathlib import Path
import sys

manual, routes, preferences = (
    json.loads(Path(path).read_text(encoding="utf-8")) for path in sys.argv[1:]
)
entry = manual["entries"]["korogus:reference"]
session = routes["sessions"]["session-reference"]
assert entry["completed"] and entry["note"] == "Conservé depuis la version précédente"
assert routes["active_session_id"] == "session-reference"
assert session["entries"][0]["tracking_id"] == "sanctuaires:reference"
assert session["entries"][0]["locked"] is True
assert preferences["values"]["map_content_mode"] == "dlc"
assert preferences["values"]["dsu_mode"] == "integrated"
PY
  fi

  local session_token
  session_token="$(printf '%s' "$identity_json" | python3 -c \
    'import json, sys; print(json.load(sys.stdin).get("session_token", ""))')"
  [[ -n "$session_token" ]] || { echo "Jeton de session absent." >&2; exit 1; }
  /usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
    -H "X-BOTW-Session-Token: $session_token" \
    -X POST "http://127.0.0.1:$port/api/shutdown" >/dev/null
  wait "$SERVER_PID"
  SERVER_PID=""
}

[[ -f "$DMG_PATH" ]] || { echo "DMG introuvable : $DMG_PATH" >&2; exit 1; }
cmake -E remove_directory "$TEST_ROOT"
mkdir -p "$CLEAN_DATA_ROOT" "$CLEAN_HOME_ROOT"

# Clean installation from the current DMG.
copy_application_from_dmg "$DMG_PATH" "$CLEAN_APPLICATION"
assert_current_application "$CLEAN_APPLICATION"
run_current_application "$CLEAN_APPLICATION" "$CLEAN_HOME_ROOT" "$CLEAN_DATA_ROOT" 18767 no

# Replace the reference version without modifying Application Support.
if [[ -n "$PREVIOUS_DMG_PATH" ]]; then
  [[ -f "$PREVIOUS_DMG_PATH" ]] || { echo "DMG de référence introuvable : $PREVIOUS_DMG_PATH" >&2; exit 1; }
  copy_application_from_dmg "$PREVIOUS_DMG_PATH" "$UPGRADE_APPLICATION"
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
    "$UPGRADE_APPLICATION/Contents/Info.plist")" == "fr.oxnight.botw-companion" ]] || {
    echo "La version de référence n'utilise pas le même identifiant de bundle." >&2
    exit 1
  }

  mkdir -p "$UPGRADE_DATA_ROOT"
  python3 - "$UPGRADE_DATA_ROOT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
timestamp = "2026-09-06T12:00:00+00:00"
payloads = {
    "manual_tracking.json": {
        "schema_version": 2, "revision": 7, "updated_at": timestamp,
        "entries": {"korogus:reference": {
            "completed": True, "note": "Conservé depuis la version précédente", "updated_at": timestamp,
        }},
    },
    "route_sessions.json": {
        "schema_version": 3, "revision": 4, "updated_at": timestamp,
        "active_session_id": "session-reference",
        "sessions": {"session-reference": {
            "id": "session-reference", "name": "Route conservée", "start": None,
            "strategy": "region", "created_at": timestamp, "updated_at": timestamp,
            "entries": [{
                "tracking_id": "sanctuaires:reference", "locked": True,
                "snapshot": {"name": "Sanctuaire conservé", "x": 12.5, "z": -8.25},
            }],
        }},
    },
    "preferences.json": {
        "schema_version": 1, "revision": 3, "updated_at": timestamp,
        "values": {"map_content_mode": "dlc", "sync_interval": 15, "dsu_mode": "integrated"},
    },
    "export-reference.json": {
        "application": "BOTW Companion", "schema_version": 2, "origine": "version précédente",
    },
}
for name, payload in payloads.items():
    (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
PY

  # Finder replaces the bundle; data remains in Application Support.
  cmake -E remove_directory "$UPGRADE_APPLICATION"
  copy_application_from_dmg "$DMG_PATH" "$UPGRADE_APPLICATION"
  assert_current_application "$UPGRADE_APPLICATION"
  run_current_application "$UPGRADE_APPLICATION" "$UPGRADE_HOME_ROOT" "" 18769 yes

  # On macOS, uninstalling means removing the bundle from Applications.
  cmake -E remove_directory "$UPGRADE_APPLICATION"
  [[ ! -e "$UPGRADE_APPLICATION" ]] || { echo "Le bundle n'a pas été supprimé." >&2; exit 1; }
  for name in manual_tracking.json route_sessions.json preferences.json export-reference.json; do
    [[ -f "$UPGRADE_DATA_ROOT/$name" ]] || {
      echo "La suppression du bundle a supprimé une donnée de référence : $name" >&2
      exit 1
    }
  done
fi

echo "DMG propre, mise à niveau, données, runtime Python, serveur et DSU arm64 validés."
