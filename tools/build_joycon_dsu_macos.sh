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
  -DJOYCON_DSU_FETCH_SDL=ON \
  -DSDL_SHARED=ON \
  -DSDL_STATIC=OFF \
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

/usr/bin/codesign --force --sign - "$PACKAGE_DIR/libSDL3.0.dylib"
/usr/bin/codesign --force --sign - "$PACKAGE_DIR/JoyConDSU"

for binary in "$PACKAGE_DIR/JoyConDSU" "$PACKAGE_DIR/libSDL3.0.dylib"; do
  if [[ "$(/usr/bin/lipo -archs "$binary")" != "arm64" ]]; then
    echo "Architecture inattendue pour $binary" >&2
    exit 1
  fi
done
if /usr/bin/otool -L "$PACKAGE_DIR/JoyConDSU" | \
    /usr/bin/grep -E '/opt/homebrew|/usr/local|/Users/' >/dev/null; then
  echo "JoyConDSU conserve une dépendance propre à la machine de construction." >&2
  exit 1
fi

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
