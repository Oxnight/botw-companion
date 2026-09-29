#!/bin/bash
set -euo pipefail

AUTHORIZED=0
TEST_MODE=0
ROOT=""
DMG=""
METADATA=""
VERSION=""
RUNTIME_VERSION=""
SHORT_VERSION=""
BUNDLE_VERSION=""
DIGEST=""
SIZE=""
PARENT_PID=""
APPLICATION=""
PORT=""
LOG=""
RELEASE_URL=""
OWNER_UID=""
OWNER_GID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --authorized) AUTHORIZED=1; shift ;;
    --test-mode) TEST_MODE=1; shift ;;
    --root) ROOT="$2"; shift 2 ;;
    --dmg) DMG="$2"; shift 2 ;;
    --metadata) METADATA="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --runtime-version) RUNTIME_VERSION="$2"; shift 2 ;;
    --short-version) SHORT_VERSION="$2"; shift 2 ;;
    --bundle-version) BUNDLE_VERSION="$2"; shift 2 ;;
    --digest) DIGEST="$2"; shift 2 ;;
    --size) SIZE="$2"; shift 2 ;;
    --parent-pid) PARENT_PID="$2"; shift 2 ;;
    --application) APPLICATION="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --log) LOG="$2"; shift 2 ;;
    --release-url) RELEASE_URL="$2"; shift 2 ;;
    --owner-uid) OWNER_UID="$2"; shift 2 ;;
    --owner-gid) OWNER_GID="$2"; shift 2 ;;
    *) exit 2 ;;
  esac
done

readonly STATE="$ROOT/installation-macos.plist"
readonly EXPECTED_NAME="BOTW_Companion_${VERSION}_macOS_arm64.dmg"
readonly BUNDLE_ID="fr.oxnight.botw-companion"
readonly DESTINATION_PARENT="$(/usr/bin/dirname "$APPLICATION")"
readonly TRANSACTION_ID="$$-$(/usr/bin/uuidgen)"
readonly STAGING="$DESTINATION_PARENT/.BOTW Companion.app.new-$TRANSACTION_ID"
readonly BACKUP="$DESTINATION_PARENT/.BOTW Companion.app.backup-$TRANSACTION_ID"
readonly MOUNT_POINT="${TMPDIR:-/tmp}/botw-companion-update-$TRANSACTION_ID"

for value in "$ROOT" "$DMG" "$METADATA" "$VERSION" "$RUNTIME_VERSION" \
  "$SHORT_VERSION" "$BUNDLE_VERSION" "$DIGEST" "$SIZE" "$PARENT_PID" \
  "$APPLICATION" "$PORT" "$LOG" "$RELEASE_URL" "$OWNER_UID" "$OWNER_GID"; do
  [[ -n "$value" ]] || exit 2
done
[[ "$ROOT" == /* && "$DMG" == "$ROOT"/* && "$METADATA" == "$ROOT"/* ]] || exit 2
[[ "$LOG" == "$ROOT"/* && "$APPLICATION" == /* ]] || exit 2
[[ "$APPLICATION" == */"BOTW Companion.app" ]] || exit 2
[[ "$DMG" == */"$EXPECTED_NAME" ]] || exit 2
[[ "$DIGEST" =~ ^[0-9a-f]{64}$ && "$SIZE" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$PARENT_PID" =~ ^[0-9]+$ && "$PORT" =~ ^[0-9]+$ ]] || exit 2
[[ "$OWNER_UID" =~ ^[0-9]+$ && "$OWNER_GID" =~ ^[0-9]+$ ]] || exit 2

/bin/mkdir -p "$(/usr/bin/dirname "$LOG")" "$ROOT"
exec >>"$LOG" 2>&1

write_state() {
  local status="$1" message="$2" can_retry="$3" rollback="$4"
  local temporary="$STATE.tmp-$$"
  /usr/bin/plutil -create xml1 "$temporary"
  /usr/bin/plutil -insert schema_version -integer 1 "$temporary"
  /usr/bin/plutil -insert status -string "$status" "$temporary"
  /usr/bin/plutil -insert version -string "$VERSION" "$temporary"
  /usr/bin/plutil -insert message -string "$message" "$temporary"
  /usr/bin/plutil -insert release_url -string "$RELEASE_URL" "$temporary"
  /usr/bin/plutil -insert can_retry -bool "$can_retry" "$temporary"
  /usr/bin/plutil -insert log_available -bool true "$temporary"
  /usr/bin/plutil -insert log_path -string "$LOG" "$temporary"
  /usr/bin/plutil -insert rollback_performed -bool "$rollback" "$temporary"
  /usr/bin/plutil -insert updated_at -integer "$(/bin/date +%s)" "$temporary"
  /bin/chmod 600 "$temporary"
  /usr/sbin/chown "$OWNER_UID:$OWNER_GID" "$temporary" 2>/dev/null || true
  /bin/mv -f "$temporary" "$STATE"
}

detach_image() {
  if /sbin/mount | /usr/bin/grep -F " on $MOUNT_POINT " >/dev/null 2>&1; then
    /usr/bin/hdiutil detach "$MOUNT_POINT" -force >/dev/null 2>&1 || true
  fi
  /bin/rmdir "$MOUNT_POINT" >/dev/null 2>&1 || true
}

cleanup() {
  detach_image
  [[ -e "$STAGING" ]] && /bin/rm -rf "$STAGING"
  relay_directory="$(cd "$(/usr/bin/dirname "$0")" 2>/dev/null && pwd -P || true)"
  if [[ "$relay_directory" == "$ROOT/relay-macos/"* ]]; then
    /bin/rm -rf "$relay_directory" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT HUP INT TERM

# Build the privileged command in JavaScript for Automation. JSON serialization
# handles quotes in paths without asking a shell to reinterpret user data.
request_authorization_safe() {
  /usr/bin/osascript -l JavaScript - "$0" "$ROOT" "$DMG" "$METADATA" \
    "$VERSION" "$RUNTIME_VERSION" "$SHORT_VERSION" "$BUNDLE_VERSION" "$DIGEST" "$SIZE" \
    "$PARENT_PID" "$APPLICATION" "$PORT" "$LOG" "$RELEASE_URL" "$OWNER_UID" "$OWNER_GID" \
    "$TEST_MODE" <<'JXA'
ObjC.import('Foundation');
function run(argv) {
  const [script, root, dmg, metadata, version, runtimeVersion, shortVersion,
    bundleVersion, digest, size, parentPid, application, port, log, releaseUrl,
    ownerUid, ownerGid, testMode] = argv;
  const args = [script, '--authorized', '--root', root, '--dmg', dmg, '--metadata', metadata,
    '--version', version, '--runtime-version', runtimeVersion, '--short-version', shortVersion,
    '--bundle-version', bundleVersion, '--digest', digest, '--size', size,
    '--parent-pid', parentPid, '--application', application, '--port', port,
    '--log', log, '--release-url', releaseUrl, '--owner-uid', ownerUid,
    '--owner-gid', ownerGid];
  if (testMode === '1') args.push('--test-mode');
  const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
  const app = Application.currentApplication();
  app.includeStandardAdditions = true;
  app.doShellScript(args.map(quote).join(' '), {administratorPrivileges: true});
}
JXA
}

validate_application() {
  local candidate="$1"
  local info="$candidate/Contents/Info.plist"
  local executable="$candidate/Contents/MacOS/BOTW Companion"
  [[ -d "$candidate" && ! -L "$candidate" && -f "$info" && -x "$executable" ]] || return 1
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$info")" == "$BUNDLE_ID" ]] || return 1
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info")" == "$SHORT_VERSION" ]] || return 1
  [[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$info")" == "$BUNDLE_VERSION" ]] || return 1
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$candidate" || return 1
  while IFS= read -r -d '' binary; do
    if /usr/bin/file -b "$binary" | /usr/bin/grep -q 'Mach-O'; then
      [[ "$(/usr/bin/lipo -archs "$binary")" == "arm64" ]] || return 1
      if /usr/bin/otool -L "$binary" | /usr/bin/tail -n +2 | \
          /usr/bin/awk '{print $1}' | /usr/bin/grep -E '^(/opt/homebrew|/usr/local|/Users/)' >/dev/null; then
        return 1
      fi
      if /usr/bin/otool -l "$binary" | /usr/bin/awk '$1 == "cmd" && $2 == "LC_RPATH" { found=1 } END { exit !found }'; then
        if /usr/bin/otool -l "$binary" | /usr/bin/awk '
          $1 == "cmd" && $2 == "LC_RPATH" { want=1; next }
          want && $1 == "path" { print $2; want=0 }
        ' | /usr/bin/grep -E '^(/opt/homebrew|/usr/local|/Users/)' >/dev/null; then
          return 1
        fi
      fi
    fi
  done < <(/usr/bin/find "$candidate" -type f -print0)
}

wait_for_parent() {
  local deadline=$((SECONDS + 45))
  [[ "$PARENT_PID" == "0" ]] && return 0
  while /bin/kill -0 "$PARENT_PID" 2>/dev/null; do
    (( SECONDS < deadline )) || return 1
    /bin/sleep 0.2
  done
}

probe_version() {
  if [[ "$TEST_MODE" == "1" && "${BOTW_UPDATE_FORCE_RESTART_FAILURE:-0}" == "1" ]]; then
    return 1
  fi
  local deadline=$((SECONDS + (TEST_MODE == 1 ? 45 : 180)))
  while (( SECONDS < deadline )); do
    if /usr/bin/curl --noproxy '*' --silent --fail --max-time 1 \
        "http://127.0.0.1:$PORT/api/version" | \
        /usr/bin/grep -F "\"version\": \"$RUNTIME_VERSION\"" >/dev/null; then
      return 0
    fi
    /bin/sleep 0.5
  done
  return 1
}

launch_application() {
  if [[ "$TEST_MODE" == "1" ]]; then
    "$APPLICATION/Contents/MacOS/BOTW Companion" --server --port "$PORT" \
      --sans-navigateur >>"$LOG" 2>&1 &
  elif [[ "$(/usr/bin/id -u)" == "0" ]]; then
    /bin/launchctl asuser "$OWNER_UID" /usr/bin/open "$APPLICATION"
  else
    /usr/bin/open "$APPLICATION"
  fi
}

write_state installing "Préparation de la mise à jour macOS…" false false

if ! wait_for_parent; then
  write_state failed "BOTW Companion ne s’est pas arrêté dans le délai prévu." true false
  exit 3
fi

if [[ ! -w "$DESTINATION_PARENT" && "$AUTHORIZED" == "0" && "$TEST_MODE" == "0" ]]; then
  write_state installing "Autorisation macOS nécessaire pour remplacer l’application…" false false
  if request_authorization_safe; then
    exit 0
  fi
  privileged_status="$(/usr/bin/plutil -extract status raw -o - "$STATE" 2>/dev/null || true)"
  if [[ "$privileged_status" == "failed" || "$privileged_status" == "cancelled" ]]; then
    exit 4
  fi
  /usr/bin/open "$APPLICATION" >/dev/null 2>&1 || true
  write_state cancelled "La mise à jour a été annulée. L’application actuelle est conservée." true false
  exit 4
fi

[[ -f "$DMG" && "$(/usr/bin/stat -f '%z' "$DMG")" == "$SIZE" ]] || {
  write_state failed "L’image disque téléchargée a changé ou est incomplète." true false
  exit 5
}
[[ "$(/usr/bin/shasum -a 256 "$DMG" | /usr/bin/awk '{print $1}')" == "$DIGEST" ]] || {
  write_state failed "L’empreinte de l’image disque ne correspond plus." true false
  exit 6
}
[[ "$(/usr/bin/plutil -extract ready raw -o - "$METADATA" 2>/dev/null)" == "true" \
  && "$(/usr/bin/plutil -extract version raw -o - "$METADATA" 2>/dev/null)" == "$VERSION" \
  && "$(/usr/bin/plutil -extract filename raw -o - "$METADATA" 2>/dev/null)" == "$EXPECTED_NAME" \
  && "$(/usr/bin/plutil -extract size raw -o - "$METADATA" 2>/dev/null)" == "$SIZE" \
  && "$(/usr/bin/plutil -extract digest raw -o - "$METADATA" 2>/dev/null)" == "sha256:$DIGEST" ]] || {
  write_state failed "Les métadonnées locales de la mise à jour ne sont plus valides." true false
  exit 7
}
/usr/bin/hdiutil verify "$DMG" >/dev/null || {
  write_state failed "L’image disque macOS est endommagée." true false
  exit 8
}

/bin/mkdir -p "$MOUNT_POINT"
/usr/bin/hdiutil attach "$DMG" -readonly -nobrowse -mountpoint "$MOUNT_POINT" >/dev/null || {
  write_state failed "L’image disque macOS ne peut pas être montée." true false
  exit 9
}
readonly SOURCE_APPLICATION="$MOUNT_POINT/BOTW Companion.app"
validate_application "$SOURCE_APPLICATION" || {
  write_state failed "Le bundle macOS ne correspond pas à la version Apple Silicon attendue." true false
  exit 10
}

required_kb=$(( $(/usr/bin/du -sk "$SOURCE_APPLICATION" | /usr/bin/awk '{print $1}') * 3 + 65536 ))
available_kb="$(/bin/df -Pk "$DESTINATION_PARENT" | /usr/bin/tail -1 | /usr/bin/awk '{print $4}')"
(( available_kb >= required_kb )) || {
  write_state failed "Espace disque insuffisant pour installer et sauvegarder l’ancienne version." true false
  exit 11
}

/usr/bin/ditto "$SOURCE_APPLICATION" "$STAGING" || {
  write_state failed "La nouvelle application n’a pas pu être copiée." true false
  exit 12
}
validate_application "$STAGING" || {
  write_state failed "La copie de la nouvelle application n’a pas passé les contrôles de sécurité." true false
  exit 13
}

write_state restarting "Installation terminée. Vérification du redémarrage…" false false
/bin/mv "$APPLICATION" "$BACKUP" || {
  write_state failed "L’application actuelle n’a pas pu être sauvegardée." true false
  exit 14
}
if ! /bin/mv "$STAGING" "$APPLICATION"; then
  /bin/mv "$BACKUP" "$APPLICATION" || true
  write_state failed "Le remplacement a échoué ; l’ancienne version a été restaurée." true true
  exit 15
fi

if launch_application && probe_version; then
  /bin/rm -rf "$BACKUP"
  /bin/rm -f "$DMG" "$METADATA"
  write_state succeeded "BOTW Companion a été mis à jour et redémarré." false false
  exit 0
fi

/bin/rm -rf "$APPLICATION"
if /bin/mv "$BACKUP" "$APPLICATION"; then
  launch_application || true
  write_state failed "La nouvelle version n’a pas démarré ; l’ancienne a été restaurée." true true
  exit 16
fi
write_state failed "La mise à jour et la restauration ont échoué. Consulte le journal avant toute nouvelle tentative." true true
exit 17
