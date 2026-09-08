#!/bin/bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Cette construction doit être exécutée sous macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "Cette version cible uniquement les Mac Apple Silicon arm64." >&2
  exit 1
fi

readonly PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly SOURCE_DIR="$PROJECT_ROOT/third_party/JoyConDSU"
readonly BUILD_DIR="$PROJECT_ROOT/build/joycon-dsu-macos-arm64"
readonly PACKAGE_DIR="$PROJECT_ROOT/botw_companion/dsu/macos"

cmake -E remove_directory "$BUILD_DIR"
mkdir -p "$PACKAGE_DIR"

cmake \
  -S "$SOURCE_DIR" \
  -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
  -DCMAKE_SKIP_BUILD_RPATH=ON \
  -DCMAKE_SKIP_RPATH=ON \
  -DJOYCON_DSU_FETCH_SDL=ON \
  -DSDL_SHARED=ON \
  -DSDL_STATIC=OFF \
  -DSDL_HIDAPI_LIBUSB=OFF \
  -DSDL_HIDAPI_LIBUSB_SHARED=OFF \
  -DCMAKE_DISABLE_FIND_PACKAGE_LibUSB=TRUE \
  -DSDL_TESTS=OFF \
  -DSDL_EXAMPLES=OFF
cmake --build "$BUILD_DIR" --config Release --parallel

readonly EXECUTABLE="$BUILD_DIR/JoyConDSU"
SDL_LIBRARY="$(find -L "$BUILD_DIR" -name 'libSDL3.0.dylib' -type f -print -quit)"
readonly SDL_LIBRARY
readonly SDL_LICENSE="$BUILD_DIR/_deps/sdl3-src/LICENSE.txt"

for required in "$EXECUTABLE" "$SDL_LIBRARY" "$SDL_LICENSE"; do
  if [[ ! -f "$required" ]]; then
    echo "Ressource native macOS manquante : $required" >&2
    exit 1
  fi
done
cmp -s "$SDL_LICENSE" "$PROJECT_ROOT/licenses/SDL3-3.4.14.txt" || {
  echo "La licence SDL3 téléchargée ne correspond pas au texte audité." >&2
  exit 1
}

/bin/cp "$EXECUTABLE" "$PACKAGE_DIR/JoyConDSU"
/bin/cp "$SDL_LIBRARY" "$PACKAGE_DIR/libSDL3.0.dylib"
/bin/cp "$SDL_LICENSE" "$PACKAGE_DIR/SDL3-LICENSE.txt"
/bin/chmod 755 "$PACKAGE_DIR/JoyConDSU" "$PACKAGE_DIR/launch_managed.sh"

SDL_DEPENDENCY="$(/usr/bin/otool -L "$PACKAGE_DIR/JoyConDSU" | \
  /usr/bin/awk '/libSDL3[^ ]*\.dylib/{print $1; exit}')"
readonly SDL_DEPENDENCY
if [[ -z "$SDL_DEPENDENCY" ]]; then
  echo "JoyConDSU n'est pas lié à SDL3." >&2
  exit 1
fi
/usr/bin/install_name_tool \
  -change "$SDL_DEPENDENCY" "@loader_path/libSDL3.0.dylib" \
  "$PACKAGE_DIR/JoyConDSU"
/usr/bin/install_name_tool \
  -id "@loader_path/libSDL3.0.dylib" \
  "$PACKAGE_DIR/libSDL3.0.dylib"

list_macho_dependencies() {
  /usr/bin/otool -L "$1" | /usr/bin/awk 'NR > 1 { print $1 }'
}

list_macho_rpaths() {
  /usr/bin/otool -l "$1" | /usr/bin/awk '
      $1 == "cmd" && $2 == "LC_RPATH" { reading_rpath = 1; next }
      reading_rpath && $1 == "path" {
        if (!seen[$2]++) print $2
        reading_rpath = 0
      }
    '
}

strip_nonportable_rpaths() {
  local binary="$1"
  local rpath

  while IFS= read -r rpath; do
    case "$rpath" in
      /Users/*|/opt/homebrew/*|/usr/local/*)
        /usr/bin/install_name_tool -delete_rpath "$rpath" "$binary"
        ;;
    esac
  done < <(list_macho_rpaths "$binary")
}

strip_nonportable_rpaths "$PACKAGE_DIR/JoyConDSU"
strip_nonportable_rpaths "$PACKAGE_DIR/libSDL3.0.dylib"

/usr/bin/codesign --force --sign - "$PACKAGE_DIR/libSDL3.0.dylib"
/usr/bin/codesign --force --sign - "$PACKAGE_DIR/JoyConDSU"

for binary in "$PACKAGE_DIR/JoyConDSU" "$PACKAGE_DIR/libSDL3.0.dylib"; do
  if [[ "$(/usr/bin/lipo -archs "$binary")" != "arm64" ]]; then
    echo "Architecture inattendue pour $binary" >&2
    exit 1
  fi
done
for binary in "$PACKAGE_DIR/JoyConDSU" "$PACKAGE_DIR/libSDL3.0.dylib"; do
  unsafe_metadata="$({ list_macho_dependencies "$binary"; list_macho_rpaths "$binary"; } | \
    /usr/bin/grep -E -C 2 '/opt/homebrew|/usr/local|/Users/' || true)"
  if [[ -n "$unsafe_metadata" ]]; then
    echo "Dépendance propre à la machine de construction : $binary" >&2
    printf '%s\n' "$unsafe_metadata" >&2
    exit 1
  fi
done

python3 - "$PACKAGE_DIR" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
payload = {
    "schema_version": 1,
    "architecture": "arm64",
    "protocol": 1001,
    "port": 26760,
    "sdl_version": "3.4.14",
    "executable_sha256": hashlib.sha256((root / "JoyConDSU").read_bytes()).hexdigest(),
    "sdl_sha256": hashlib.sha256((root / "libSDL3.0.dylib").read_bytes()).hexdigest(),
}
(root / "manifest.json").write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo "Moteur JoyConDSU macOS arm64 construit dans $PACKAGE_DIR"
