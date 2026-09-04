#!/bin/bash
set -euo pipefail

SKIP_NATIVE=0
KEEP_BUILD_ENVIRONMENT=0
for argument in "$@"; do
  case "$argument" in
    --skip-native) SKIP_NATIVE=1 ;;
    --keep-build-environment) KEEP_BUILD_ENVIRONMENT=1 ;;
    *) echo "Option inconnue : $argument" >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Le paquet doit être construit sur un Mac Apple Silicon." >&2
  exit 1
fi

readonly PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly BUILD_ROOT="$PROJECT_ROOT/build/macos-package"
readonly BUILD_PYTHON="$BUILD_ROOT/venv/bin/python"
readonly SPEC_PATH="$PROJECT_ROOT/macos/BOTW Companion.spec"
readonly APPLICATION="$PROJECT_ROOT/dist/BOTW Companion.app"
readonly DMG_ROOT="$BUILD_ROOT/dmg-root"
readonly DMG_PATH="$PROJECT_ROOT/dist/BOTW_Companion_0.40.0-alpha.24_macOS_arm64.dmg"

if [[ $SKIP_NATIVE -eq 0 ]]; then
  "$PROJECT_ROOT/tools/build_joycon_dsu_macos.sh"
fi

for required in \
  "$PROJECT_ROOT/botw_companion/dsu/macos/JoyConDSU" \
  "$PROJECT_ROOT/botw_companion/dsu/macos/libSDL3.0.dylib" \
  "$PROJECT_ROOT/botw_companion/dsu/macos/launch_managed.sh" \
  "$PROJECT_ROOT/botw_companion/dsu/macos/manifest.json" \
  "$PROJECT_ROOT/botw_companion/dsu/macos/SDL3-LICENSE.txt"; do
  [[ -f "$required" ]] || { echo "Ressource macOS manquante : $required" >&2; exit 1; }
done

cmake -E remove_directory "$PROJECT_ROOT/dist"
cmake -E remove_directory "$DMG_ROOT"
mkdir -p "$BUILD_ROOT" "$DMG_ROOT"

if [[ ! -x "$BUILD_PYTHON" ]]; then
  python3 -m venv "$BUILD_ROOT/venv"
fi
"$BUILD_PYTHON" -m pip install \
  --disable-pip-version-check \
  --quiet \
  "pyinstaller==6.22.2"

cd "$PROJECT_ROOT"
"$BUILD_PYTHON" -m PyInstaller --noconfirm --clean "$SPEC_PATH"

[[ -d "$APPLICATION" ]] || { echo "L'application macOS n'a pas été produite." >&2; exit 1; }
PACKAGED_DSU="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/JoyConDSU' -type f -print -quit)"
PACKAGED_SDL="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/libSDL3.0.dylib' -type f -print -quit)"
PACKAGED_LAUNCHER="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/launch_managed.sh' -type f -print -quit)"
PACKAGED_MANIFEST="$(find "$APPLICATION" -path '*/botw_companion/dsu/macos/manifest.json' -type f -print -quit)"
[[ -n "$PACKAGED_DSU" && -n "$PACKAGED_SDL" && -n "$PACKAGED_LAUNCHER" \
  && -n "$PACKAGED_MANIFEST" ]] || {
  echo "Le moteur DSU n'est pas présent dans l'application." >&2
  exit 1
}
/bin/chmod 755 "$PACKAGED_DSU" "$PACKAGED_LAUNCHER"

# PyInstaller signe déjà ses binaires en mode ad hoc. Le moteur ajouté au paquet
# est néanmoins signé explicitement, de l'intérieur vers l'extérieur. Ne pas
# utiliser --deep pour signer : --force --deep modifierait à nouveau les binaires
# après le calcul de leurs empreintes dans le manifeste.
/usr/bin/codesign --force --sign - "$PACKAGED_SDL"
/usr/bin/codesign --force --sign - "$PACKAGED_DSU"
python3 - "$PACKAGED_MANIFEST" "$PACKAGED_DSU" "$PACKAGED_SDL" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

manifest_path, executable_path, sdl_path = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["executable_sha256"] = hashlib.sha256(executable_path.read_bytes()).hexdigest()
manifest["sdl_sha256"] = hashlib.sha256(sdl_path.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
/usr/bin/codesign --force --sign - "$APPLICATION"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APPLICATION"
"$APPLICATION/Contents/MacOS/BOTW Companion" --package-self-test

/usr/bin/ditto "$APPLICATION" "$DMG_ROOT/BOTW Companion.app"
/bin/ln -s /Applications "$DMG_ROOT/Applications"
/usr/bin/hdiutil create \
  -volname "BOTW Companion" \
  -srcfolder "$DMG_ROOT" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

if [[ $KEEP_BUILD_ENVIRONMENT -eq 0 ]]; then
  cmake -E remove_directory "$BUILD_ROOT/venv"
fi

echo "Application autonome : $APPLICATION"
echo "Image disque : $DMG_PATH"
