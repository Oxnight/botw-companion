#!/bin/zsh
set -u

readonly BINARY="$1"
readonly PARENT_PID="$2"
shift 2
readonly EXTRA_ARGS=("$@")
readonly PROJECT_ROOT="${0:A:h:h:h}"
readonly SOURCE_DIR="$PROJECT_ROOT/third_party/JoyConDSU/Sources/JoyConDSU"
readonly CACHE_DIR="$HOME/Library/Application Support/BOTW Companion/native"
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

build_native_runtime() {
  local compiler sdk_path sdl_prefix source source_hash runtime temporary
  compiler="$(/usr/bin/xcrun --sdk macosx --find clang 2>/dev/null)" || {
    print -u2 -- "Compilateur Apple introuvable. Installe les outils de ligne de commande Xcode."
    return 1
  }
  sdk_path="$(/usr/bin/xcrun --sdk macosx --show-sdk-path 2>/dev/null)" || {
    print -u2 -- "SDK macOS introuvable. Installe ou répare les outils de ligne de commande Xcode."
    return 1
  }
  [[ -d "$sdk_path" ]] || {
    print -u2 -- "SDK macOS invalide : $sdk_path"
    return 1
  }
  sdl_prefix="$(/opt/homebrew/bin/brew --prefix sdl3 2>/dev/null)" || {
    print -u2 -- "SDL3 introuvable. Installe-le avec : brew install sdl3"
    return 1
  }

  for source in main.c calibration.c calibration.h dsu_clients.c dsu_clients.h dsu_protocol.c dsu_protocol.h motion_pipeline.c motion_pipeline.h telemetry.c telemetry.h platform_socket.h platform_socket_posix.c platform_runtime.h platform_runtime_posix.c; do
    [[ -f "$SOURCE_DIR/$source" ]] || {
      print -u2 -- "Source native manquante : $source"
      return 1
    }
  done

  source_hash="$(
    /usr/bin/shasum -a 256 \
      "$SOURCE_DIR/main.c" \
      "$SOURCE_DIR/calibration.c" \
      "$SOURCE_DIR/calibration.h" \
      "$SOURCE_DIR/dsu_clients.c" \
      "$SOURCE_DIR/dsu_clients.h" \
      "$SOURCE_DIR/dsu_protocol.c" \
      "$SOURCE_DIR/dsu_protocol.h" \
      "$SOURCE_DIR/motion_pipeline.c" \
      "$SOURCE_DIR/motion_pipeline.h" \
      "$SOURCE_DIR/telemetry.c" \
      "$SOURCE_DIR/telemetry.h" \
      "$SOURCE_DIR/platform_socket.h" \
      "$SOURCE_DIR/platform_socket_posix.c" \
      "$SOURCE_DIR/platform_runtime.h" \
      "$SOURCE_DIR/platform_runtime_posix.c" \
      | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
  )"
  /bin/mkdir -p "$CACHE_DIR"
  runtime="$CACHE_DIR/JoyConDSU-$source_hash"

  if [[ ! -x "$runtime" ]]; then
    temporary="$runtime.tmp.$$"
    SDKROOT="$sdk_path" "$compiler" \
      -isysroot "$sdk_path" \
      -std=c17 -O2 -DNDEBUG -arch arm64 \
      -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wformat=2 \
      -I"$sdl_prefix/include" \
      "$SOURCE_DIR/main.c" \
      "$SOURCE_DIR/calibration.c" \
      "$SOURCE_DIR/dsu_clients.c" \
      "$SOURCE_DIR/dsu_protocol.c" \
      "$SOURCE_DIR/motion_pipeline.c" \
      "$SOURCE_DIR/telemetry.c" \
      "$SOURCE_DIR/platform_socket_posix.c" \
      "$SOURCE_DIR/platform_runtime_posix.c" \
      -L"$sdl_prefix/lib" \
      -Wl,-rpath,"$sdl_prefix/lib" \
      -lSDL3 -lm \
      -o "$temporary" || {
        /bin/rm -f "$temporary"
        print -u2 -- "Compilation native JoyConDSU impossible."
        return 1
      }
    /bin/chmod 755 "$temporary"
    /bin/mv "$temporary" "$runtime"
  fi

  print -r -- "$runtime"
}

# Le Companion peut être lancé par un Python Intel sous Rosetta 2. Demander
# explicitement la tranche ARM évite que cette architecture soit héritée par
# le sous-processus JoyConDSU sur un Mac Apple Silicon.
RUNTIME="$(build_native_runtime)" || {
  if [[ "${EXTRA_ARGS[1]:-}" == "--list-controllers" ]]; then
    print -u2 -- "Inventaire des manettes impossible sans runtime natif à jour."
    exit 1
  fi
  if [[ -x "$BINARY" ]]; then
    print -u2 -- "Repli sur le binaire JoyConDSU intégré."
    RUNTIME="$BINARY"
  else
    exit 1
  fi
}
readonly RUNTIME

if [[ "${EXTRA_ARGS[1]:-}" == "--list-controllers" ]]; then
  /usr/bin/arch -arm64 "$RUNTIME" "${EXTRA_ARGS[@]}"
  exit $?
fi

/usr/bin/arch -arm64 "$RUNTIME" "${EXTRA_ARGS[@]}" &
child_pid=$!

while /bin/kill -0 "$child_pid" 2>/dev/null; do
  if ! /bin/kill -0 "$PARENT_PID" 2>/dev/null; then
    exit 0
  fi
  /bin/sleep 1
done

# Le test kill ci-dessus constate que macOS a déjà récolté le processus.
# Un second `wait` produit alors inutilement « pid is not a child » dans zsh.
child_pid=""