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
PARENT_STOPPED=0
RECOVERY_HANDLED=0
COMMITTED=0
SWAPPED=0
LAUNCHED_PID=""
ORIGINAL_RUNTIME_VERSION=""
IMAGE_ATTACHED=0

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
[[ "$METADATA" == "$DMG.metadata.json" && ! -L "$DMG" && ! -L "$METADATA" ]] || exit 2
[[ "$DIGEST" =~ ^[0-9a-f]{64}$ && "$SIZE" =~ ^[1-9][0-9]*$ ]] || exit 2
[[ "$PARENT_PID" =~ ^[0-9]+$ && "$PORT" =~ ^[0-9]+$ ]] || exit 2
(( PORT >= 1 && PORT <= 65535 )) || exit 2
[[ "$RELEASE_URL" == "https://github.com/Oxnight/botw-companion/releases/tag/v$VERSION" ]] || exit 2
[[ "$OWNER_UID" =~ ^[0-9]+$ && "$OWNER_GID" =~ ^[0-9]+$ ]] || exit 2

/bin/mkdir -p "$(/usr/bin/dirname "$LOG")" "$ROOT"
exec >>"$LOG" 2>&1
printf 'Application: %s\nStaging: %s\nBackup: %s\n' "$APPLICATION" "$STAGING" "$BACKUP"

write_state() {
  local status="$1" message="$2" can_retry="$3" rollback="$4"
  local temporary="$STATE.tmp-$$"
  /usr/bin/plutil -create xml1 "$temporary"
  /usr/bin/plutil -insert schema_version -integer 1 "$temporary"
  /usr/bin/plutil -insert relay_pid -integer "$$" "$temporary"
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
  local attempt
  # mount prints canonical /private/var paths while TMPDIR can use /var.
  # Detach the image this relay attached, without comparing display paths.
  if [[ "$IMAGE_ATTACHED" == "1" ]]; then
    for attempt in 1 2 3; do
      if /usr/bin/hdiutil detach "$MOUNT_POINT" >/dev/null; then
        IMAGE_ATTACHED=0
        break
      fi
      [[ "$attempt" == "3" ]] || /bin/sleep 0.2
    done
    if [[ "$IMAGE_ATTACHED" == "1" ]]; then
      /usr/bin/hdiutil detach "$MOUNT_POINT" -force >/dev/null || return 1
      IMAGE_ATTACHED=0
    fi
  fi
  /bin/rmdir "$MOUNT_POINT" >/dev/null 2>&1 || true
}

cleanup() {
  detach_image || printf 'The owned disk image could not be detached: %s\n' "$MOUNT_POINT" >&2
  [[ -e "$STAGING" ]] && /bin/rm -rf "$STAGING"
  relay_directory="$(cd "$(/usr/bin/dirname "$0")" 2>/dev/null && pwd -P || true)"
  if [[ "$relay_directory" == "$ROOT/relay-macos/"* ]]; then
    /bin/rm -rf "$relay_directory" >/dev/null 2>&1 || true
  fi
}

finish_relay() {
  local result=$?
  trap - EXIT HUP INT TERM
  set +e
  if (( result != 0 && PARENT_STOPPED == 1 && RECOVERY_HANDLED == 0 && COMMITTED == 0 )); then
    if [[ "$SWAPPED" == "1" && -d "$BACKUP" ]]; then
      if restore_backup; then
        write_state failed "La mise à jour a échoué ; l’ancienne version a été restaurée." true true
      else
        write_state failed "La restauration n’a pas pu être terminée. La sauvegarde est conservée ; consulte le journal." true false
      fi
    else
      launch_application || true
      if [[ "$TEST_MODE" == "1" ]]; then
        wait_for_version "${ORIGINAL_RUNTIME_VERSION:-$RUNTIME_VERSION}" || true
      fi
      current_status="$(/usr/bin/plutil -extract status raw -o - "$STATE" 2>/dev/null)"
      if [[ "$current_status" != "failed" && "$current_status" != "cancelled" ]]; then
        write_state failed "Le relais macOS a été interrompu. L’application actuelle est conservée." true false
      fi
    fi
  fi
  cleanup
  exit "$result"
}
trap finish_relay EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

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

wait_for_version() {
  local expected="$1"
  local deadline=$((SECONDS + (TEST_MODE == 1 ? 45 : 180)))
  while (( SECONDS < deadline )); do
    local identity
    identity="$(/usr/bin/curl --noproxy '*' --silent --fail --max-time 1 \
        "http://127.0.0.1:$PORT/api/version" 2>/dev/null || true)"
    if [[ "$(printf '%s' "$identity" | /usr/bin/plutil -extract application raw -o - - 2>/dev/null)" == "BOTW Companion" \
      && "$(printf '%s' "$identity" | /usr/bin/plutil -extract version raw -o - - 2>/dev/null)" == "$expected" ]]; then
      return 0
    fi
    /bin/sleep 0.5
  done
  return 1
}

probe_version() {
  if [[ "$TEST_MODE" == "1" && "${BOTW_UPDATE_FORCE_RESTART_FAILURE:-0}" == "1" ]]; then
    return 1
  fi
  wait_for_version "$RUNTIME_VERSION"
}

launch_application() {
  if [[ "$TEST_MODE" == "1" ]]; then
    "$APPLICATION/Contents/MacOS/BOTW Companion" --server --port "$PORT" \
      --sans-navigateur >>"$LOG" 2>&1 &
    LAUNCHED_PID=$!
  elif [[ "$(/usr/bin/id -u)" == "0" ]]; then
    # asuser selects the GUI session; sudo also drops root credentials.
    /bin/launchctl asuser "$OWNER_UID" /usr/bin/sudo -H -u "#$OWNER_UID" \
      /usr/bin/open "$APPLICATION" --args --port "$PORT"
  else
    /usr/bin/open "$APPLICATION" --args --port "$PORT"
  fi
}

stop_new_application() {
  local deadline=$((SECONDS + 45))
  if [[ -n "$LAUNCHED_PID" ]]; then
    /bin/kill -TERM "$LAUNCHED_PID" 2>/dev/null || true
    while /bin/kill -0 "$LAUNCHED_PID" 2>/dev/null; do
      if (( SECONDS >= deadline )); then
        /bin/kill -KILL "$LAUNCHED_PID" 2>/dev/null || true
        break
      fi
      /bin/sleep 0.2
    done
    wait "$LAUNCHED_PID" 2>/dev/null || true
    LAUNCHED_PID=""
    return 0
  fi
  local identity application_name version token pid
  identity="$(/usr/bin/curl --noproxy '*' --silent --fail --max-time 2 \
    "http://127.0.0.1:$PORT/api/version" 2>/dev/null || true)"
  application_name="$(printf '%s' "$identity" | /usr/bin/plutil -extract application raw -o - - 2>/dev/null)"
  version="$(printf '%s' "$identity" | /usr/bin/plutil -extract version raw -o - - 2>/dev/null)"
  token="$(printf '%s' "$identity" | /usr/bin/plutil -extract session_token raw -o - - 2>/dev/null)"
  pid="$(printf '%s' "$identity" | /usr/bin/plutil -extract process_id raw -o - - 2>/dev/null)"
  # An unconfirmed process must never trigger destructive bundle replacement.
  [[ "$application_name" == "BOTW Companion" && "$version" == "$RUNTIME_VERSION" \
    && "$token" =~ ^[a-zA-Z0-9_-]+$ && "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  /usr/bin/curl --noproxy '*' --silent --fail --max-time 10 \
    -H "X-BOTW-Session-Token: $token" -X POST \
    "http://127.0.0.1:$PORT/api/shutdown" >/dev/null || return 1
  while /bin/kill -0 "$pid" 2>/dev/null; do
    (( SECONDS < deadline )) || return 1
    /bin/sleep 0.2
  done
}

restore_backup() {
  [[ -d "$BACKUP" ]] || return 1
  if [[ -d "$APPLICATION" ]]; then
    stop_new_application || return 1
    atomic_swap "$APPLICATION" "$BACKUP" || return 1
  else
    /bin/mv "$BACKUP" "$APPLICATION" || return 1
  fi
  launch_application || return 1
  # A successful GUI open is not proof that the restored server started.
  wait_for_version "$ORIGINAL_RUNTIME_VERSION" || return 1
  # After exchange this slot contains the rejected new bundle, not the old one.
  /bin/rm -rf "$BACKUP" || true
}

atomic_swap() {
  # Both bundles are on the destination volume. Never fall back to two moves:
  # that would make the Dock target disappear if the relay is killed midway.
  /usr/bin/osascript -l JavaScript - "$1" "$2" <<'SWAP_JXA'
ObjC.bindFunction('renamex_np', ['int', ['char *', 'char *', 'unsigned int']]);
function run(argv) {
  if (argv.length !== 2 || $.renamex_np(argv[0], argv[1], 2) !== 0) {
    throw new Error('Atomic bundle exchange failed; both bundles are retained.');
  }
}
SWAP_JXA
}

original_version_file="$(/usr/bin/find "$APPLICATION" -path '*/botw_companion/VERSION' -type f -print -quit)"
ORIGINAL_RUNTIME_VERSION="$(/bin/cat "$original_version_file" 2>/dev/null || true)"
[[ "$ORIGINAL_RUNTIME_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-(alpha|beta|rc)\.[0-9]+)?$ ]] || {
  write_state failed "La version de l’application actuelle ne peut pas être vérifiée." true false
  exit 14
}
ORIGINAL_RUNTIME_VERSION="${ORIGINAL_RUNTIME_VERSION/-alpha./a}"
ORIGINAL_RUNTIME_VERSION="${ORIGINAL_RUNTIME_VERSION/-beta./b}"
ORIGINAL_RUNTIME_VERSION="${ORIGINAL_RUNTIME_VERSION/-rc./rc}"


write_state installing "Préparation de la mise à jour macOS…" false false

if ! wait_for_parent; then
  write_state failed "BOTW Companion ne s’est pas arrêté dans le délai prévu." true false
  exit 3
fi
PARENT_STOPPED=1

if [[ ! -w "$DESTINATION_PARENT" && "$AUTHORIZED" == "0" && "$TEST_MODE" == "0" ]]; then
  write_state installing "Autorisation macOS nécessaire pour remplacer l’application…" false false
  # The authorized relay owns recovery while the authorization call is active.
  # A signal to this waiting wrapper must not reopen the bundle mid-replacement.
  RECOVERY_HANDLED=1
  if request_authorization_safe; then
    RECOVERY_HANDLED=1
    exit 0
  fi
  privileged_status="$(/usr/bin/plutil -extract status raw -o - "$STATE" 2>/dev/null || true)"
  if [[ "$privileged_status" == "failed" || "$privileged_status" == "cancelled" ]]; then
    RECOVERY_HANDLED=1
    exit 4
  fi
  RECOVERY_HANDLED=0
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
IMAGE_ATTACHED=1
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

# No installed bundle uses the source image after ditto and validation.
# Release it before publication, so SIGKILL cannot leave the retry DMG busy.
detach_image || {
  write_state failed "L’image disque macOS ne peut pas être démontée." true false
  exit 18
}

write_state restarting "Installation terminée. Vérification du redémarrage…" false false
# Move the validated NEW bundle into the backup slot first. The application
# remains at its original path until the single atomic exchange succeeds.
/bin/mv "$STAGING" "$BACKUP" || {
  write_state failed "La nouvelle application n’a pas pu être préparée pour le remplacement." true false
  exit 14
}
if ! atomic_swap "$APPLICATION" "$BACKUP"; then
  write_state failed "Le remplacement atomique a échoué. L’application actuelle est conservée." true false
  exit 15
fi
SWAPPED=1

# Native CI kills the relay after publication; normal runs cannot activate it.
if [[ "$TEST_MODE" == "1" && "${BOTW_UPDATE_KILL_AFTER_SWAP:-0}" == "1" ]]; then
  /bin/kill -KILL "$$"
fi

if launch_application && probe_version; then
  COMMITTED=1
  write_state succeeded "BOTW Companion a été mis à jour et redémarré." false false
  /bin/rm -rf "$BACKUP" || true
  /bin/rm -f "$DMG" "$METADATA" || true
  exit 0
fi

RECOVERY_HANDLED=1
if restore_backup; then
  write_state failed "La nouvelle version n’a pas démarré ; l’ancienne a été restaurée." true true
  exit 16
fi
write_state failed "Le redémarrage et la restauration n’ont pas pu être confirmés. La sauvegarde est conservée ; consulte le journal." true false
exit 17
