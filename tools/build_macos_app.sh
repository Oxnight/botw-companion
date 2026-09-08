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
readonly DMG_NAME="$(python3 "$PROJECT_ROOT/tools/release_metadata.py" --field dmg_name)"
readonly DMG_PATH="$PROJECT_ROOT/dist/$DMG_NAME"
readonly DMG_WORK_ROOT="${RUNNER_TEMP:-/tmp}/botw-companion-dmg-$$"
readonly DMG_ROOT="$DMG_WORK_ROOT/root"
readonly TEMP_DMG_PATH="$DMG_WORK_ROOT/$DMG_NAME"

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
cmp -s "$PROJECT_ROOT/botw_companion/dsu/macos/SDL3-LICENSE.txt" \
  "$PROJECT_ROOT/licenses/SDL3-3.4.14.txt" || {
  echo "La licence SDL3 générée ne correspond pas au texte audité." >&2
  exit 1
}

cmake -E remove_directory "$PROJECT_ROOT/dist"
cmake -E remove_directory "$DMG_WORK_ROOT"
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
PACKAGED_LOCALIZATION="$(find "$APPLICATION" -path '*/botw_companion/data/localization_fr.json' -type f -print -quit)"
PACKAGED_NOMENCLATURE="$(find "$APPLICATION" -path '*/botw_companion/data/nomenclature_fr_reference.json' -type f -print -quit)"
[[ -n "$PACKAGED_DSU" && -n "$PACKAGED_SDL" && -n "$PACKAGED_LAUNCHER" \
  && -n "$PACKAGED_MANIFEST" && -n "$PACKAGED_LOCALIZATION" \
  && -n "$PACKAGED_NOMENCLATURE" ]] || {
  echo "Le moteur DSU n'est pas présent dans l'application." >&2
  exit 1
}
for document in LICENSE CHANGELOG.md THIRD_PARTY_NOTICES.md DATA_SOURCES.md PRIVACY.md SECURITY.md \
  licenses/PYTHON-3.12.txt licenses/SDL3-3.4.14.txt; do
  find "$APPLICATION" -path "*/$document" -type f -print -quit | grep -q . || {
    echo "Document absent de l'application macOS : $document" >&2; exit 1;
  }
done
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

# hdiutil peut répondre transitoirement « Resource busy » sur les runners macOS
# hébergés. La source et l'image temporaire restent hors du dépôt, chaque essai
# repart d'un fichier absent et le résultat est vérifié avant publication.
dmg_created=0
for attempt in 1 2 3 4; do
  cmake -E rm -f "$TEMP_DMG_PATH"
  if /usr/bin/hdiutil create \
      -volname "BOTW Companion" \
      -srcfolder "$DMG_ROOT" \
      -ov \
      -format UDZO \
      "$TEMP_DMG_PATH"; then
    dmg_created=1
    break
  fi
  echo "Création du DMG indisponible (essai $attempt/4), nouvelle tentative." >&2
  /bin/sleep $((attempt * 2))
done
[[ $dmg_created -eq 1 ]] || { echo "Impossible de créer le DMG après 4 essais." >&2; exit 1; }
/usr/bin/hdiutil verify "$TEMP_DMG_PATH"
/bin/mv -f "$TEMP_DMG_PATH" "$DMG_PATH"
cmake -E remove_directory "$DMG_WORK_ROOT"

if [[ $KEEP_BUILD_ENVIRONMENT -eq 0 ]]; then
  cmake -E remove_directory "$BUILD_ROOT/venv"
fi

echo "Application autonome : $APPLICATION"
echo "Image disque : $DMG_PATH"
