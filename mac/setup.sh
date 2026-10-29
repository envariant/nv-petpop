#!/usr/bin/env bash
# PetPop GenAI host setup for an Apple Silicon Mac (profile mac-m4pro). Idempotent; re-run after a git pull.
#
#   cd nv-petpop && mac/setup.sh          # or: make -C mac setup
#
# Deterministic: everything it installs is pinned in this repo and checked before use, and it never runs an
# upstream installer.
#   - Tools (uv, ollama, caddy, cloudflared): exact releases from mac/tools.lock, hash-checked before unpacking,
#     into $PETPOP_GENAI/opt; no Homebrew.
#   - Python: the exact CPython in mac/tools.lock, installed by the pinned uv (which checks its hash).
#   - Venvs (comfyui, shape, tools): `uv pip sync --require-hashes` from mac/locks/*.txt (wheels only), so each
#     venv holds exactly the locked packages and nothing else.
#   - Code (ComfyUI, ComfyUI_IPAdapter_plus, hunyuan3d-2.1-mac, Tencent's Hunyuan3D-2.1): git checkouts at the
#     commits in pipelines/comfy/requirements.txt, with the commit checked after checkout.
#   - The Ollama model: pulled by tag, then its manifest digest is checked against pipelines/comfy/models.yaml.
# Weights are separate: `make -C mac models` fetches them and checks every file against models.lock.json.
# The only prerequisite is the Xcode Command Line Tools (xcode-select --install).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PETPOP_GENAI="${PETPOP_GENAI:-$HOME/petpop-genai}"
PETPOP_MODELS="${PETPOP_MODELS:-$HOME/petpop-models}"
PINS="$REPO/pipelines/comfy/requirements.txt"
TOOLS="$REPO/mac/tools.lock"
OPT="$PETPOP_GENAI/opt"
VENVS="$PETPOP_GENAI/venvs"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { echo "setup: $*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || die "mac/setup.sh is for Apple Silicon macOS"
xcode-select -p >/dev/null 2>&1 || die "install the Xcode Command Line Tools first: xcode-select --install"
mkdir -p "$PETPOP_GENAI/logs" "$PETPOP_GENAI/bin" "$OPT" "$VENVS" "$PETPOP_MODELS"

# ---------------------------------------------------------------- tools
tool() { awk -v n="$1" '$1==n {print $'"$2"'}' "$TOOLS"; }

fetch_checked() {  # fetch_checked url algo:hash out
  local url="$1" algo="${2%%:*}" want="${2#*:}" out="$3" got
  curl -fsSL --retry 3 "$url" -o "$out.part"
  case "$algo" in
    sha256) got="$(shasum -a 256 "$out.part" | awk '{print $1}')" ;;
    sha512) got="$(shasum -a 512 "$out.part" | awk '{print $1}')" ;;
    *) die "unknown hash $algo for $url" ;;
  esac
  [ "$got" = "$want" ] || { rm -f "$out.part"; die "$url: $algo $got is not the pinned $want"; }
  mv "$out.part" "$out"
}

install_tool() {  # install_tool name binary-inside-archive
  local name="$1" inner="$2" version hash url dir archive
  version="$(tool "$name" 2)"; hash="$(tool "$name" 3)"; url="$(tool "$name" 4)"
  dir="$OPT/$name-$version"
  if [ ! -x "$dir/$inner" ]; then
    archive="$OPT/${url##*/}"
    fetch_checked "$url" "$hash" "$archive"
    rm -rf "$dir.tmp" && mkdir -p "$dir.tmp"
    case "$archive" in
      *.whl) unzip -q "$archive" "$inner" -d "$dir.tmp" ;;
      *) tar -xzf "$archive" -C "$dir.tmp" ;;
    esac
    rm -f "$archive"
    rm -rf "$dir" && mv "$dir.tmp" "$dir"
    chmod +x "$dir/$inner"
  fi
  ln -sfn "$dir/$inner" "$PETPOP_GENAI/bin/$name"
  echo "$name $version"
}

say "Tools (mac/tools.lock)"
UV_VERSION="$(tool uv 2)"
install_tool uv "uv-$UV_VERSION.data/scripts/uv"
install_tool ollama ollama
install_tool caddy caddy
install_tool cloudflared cloudflared
export PATH="$PETPOP_GENAI/bin:$PATH"
[ "$(uv --version | awk '{print $2}')" = "$UV_VERSION" ] || die "uv is not $UV_VERSION"

# uv: pinned Python under $PETPOP_GENAI, no user or project config, no implicit Python downloads.
export UV_PYTHON_INSTALL_DIR="$PETPOP_GENAI/python" UV_NO_CONFIG=1 UV_PYTHON_DOWNLOADS=manual UV_CACHE_DIR="$PETPOP_GENAI/cache/uv"
PY_VERSION="$(tool python 2)"
say "Python $PY_VERSION"
uv python install "$PY_VERSION"

venv_sync() {  # venv_sync name
  local v="$VENVS/$1"
  if [ ! -x "$v/bin/python" ] || [ "$("$v/bin/python" -c 'import platform; print(platform.python_version())')" != "$PY_VERSION" ]; then
    rm -rf "$v" && uv venv --quiet --managed-python --python "$PY_VERSION" "$v"
  fi
  uv pip sync --quiet --python "$v/bin/python" --require-hashes --only-binary :all: "$REPO/mac/locks/$1.txt"
  echo "venv $1: $(uv pip list --python "$v/bin/python" 2>/dev/null | tail -n +3 | wc -l | tr -d ' ') packages from mac/locks/$1.txt"
}

# ---------------------------------------------------------------- code
pin() { awk -v n="$1" '$1==n {print $2" "$3}' "$PINS"; }
clone_at() {  # clone_at name dir
  local url commit
  read -r url commit < <(pin "$1")
  [ -n "$commit" ] || die "$1 is not pinned in $PINS"
  [ -d "$2/.git" ] || git clone --quiet --no-checkout "$url" "$2"
  git -C "$2" cat-file -e "$commit^{commit}" 2>/dev/null || git -C "$2" fetch --quiet origin "$commit" || git -C "$2" fetch --quiet origin
  git -C "$2" checkout --quiet --force --detach "$commit"
  [ "$(git -C "$2" rev-parse HEAD)" = "$commit" ] || die "$1 is not at $commit"
  echo "$1 @ ${commit:0:12}"
}

say "ComfyUI (MPS)"
clone_at ComfyUI "$PETPOP_GENAI/ComfyUI"
clone_at ComfyUI_IPAdapter_plus "$PETPOP_GENAI/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus"
clone_at ComfyUI-MVAdapter "$PETPOP_GENAI/ComfyUI/custom_nodes/ComfyUI-MVAdapter"   # its packages are in the comfyui lock
venv_sync comfyui
sed "s#__MODELS__#$PETPOP_MODELS#g" "$REPO/mac/comfy_extra_model_paths.yaml.in" > "$PETPOP_GENAI/ComfyUI/extra_model_paths.yaml"
mkdir -p "$PETPOP_MODELS"/{checkpoints,vae,controlnet,ipadapter,clip_vision,loras,diffusion_models,hf,diffusers}
# MV-Adapter loads diffusers-format folders by path, relative to ComfyUI's working directory, so the profile names
# them as petpop-models/<dest> and never an absolute host path.
ln -sfn "$PETPOP_MODELS" "$PETPOP_GENAI/ComfyUI/petpop-models"

say "Hunyuan3D-2.1 shape (MPS fork + upstream code; the fork's install.sh is not run)"
clone_at hunyuan3d-2.1-mac "$PETPOP_GENAI/hunyuan3d-2.1-mac"
clone_at Hunyuan3D-2.1 "$PETPOP_GENAI/hunyuan3d-2.1-mac/Hunyuan3D-2.1"   # where the fork expects it
venv_sync shape
venv_sync tools

say "Ollama model"
read -r OLLAMA_TAG OLLAMA_DIGEST < <("$VENVS/tools/bin/python" - "$REPO/pipelines/comfy/models.yaml" <<'PY'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1]))["ollama"][0]
print(m["tag"], m["manifest_digest"].split(":", 1)[1])
PY
)
export OLLAMA_MODELS="$PETPOP_GENAI/ollama"
OLLAMA_BIN="$(readlink "$PETPOP_GENAI/bin/ollama")"   # the real path: Ollama loads its runners from beside it
launchctl bootout "gui/$(id -u)/com.petpop.ollama" 2>/dev/null || true   # free the port; reloaded below
OLLAMA_HOST=127.0.0.1:11434 "$OLLAMA_BIN" serve >"$PETPOP_GENAI/logs/ollama-setup.log" 2>&1 & OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -fs http://127.0.0.1:11434/api/version >/dev/null && break; sleep 1; done
OLLAMA_HOST=127.0.0.1:11434 "$OLLAMA_BIN" pull "$OLLAMA_TAG"
GOT="$(curl -fs http://127.0.0.1:11434/api/tags | "$VENVS/tools/bin/python" -c "
import json, sys
print(next((m['digest'] for m in json.load(sys.stdin)['models'] if m['name'] == '$OLLAMA_TAG'), ''))")"
kill "$OLLAMA_PID" 2>/dev/null || true; trap - EXIT
GOT="${GOT#sha256:}"
[ "$GOT" = "$OLLAMA_DIGEST" ] || die "$OLLAMA_TAG has manifest digest $GOT, not the pinned $OLLAMA_DIGEST (the tag moved upstream)"
echo "$OLLAMA_TAG @ ${OLLAMA_DIGEST:0:12}"

say "Secrets ($PETPOP_GENAI/genai.env)"
if [ ! -f "$PETPOP_GENAI/genai.env" ]; then
  ( umask 077
    cat > "$PETPOP_GENAI/genai.env" <<ENV
GENAI_PROFILE=mac-m4pro
GENAI_TOKEN=$(openssl rand -hex 24)
PETPOP_MODELS=$PETPOP_MODELS
HY3D_DIR=$PETPOP_GENAI/hunyuan3d-2.1-mac
PETPOP_PROXY_PORT=8787
ENV
  )
fi
echo "GENAI_TOKEN is in $PETPOP_GENAI/genai.env (chmod 600)"

say "launchd units"
mkdir -p "$HOME/Library/LaunchAgents"
for unit in comfyui shape ollama; do
  src="$REPO/mac/launchd/com.petpop.$unit.plist.in"
  dst="$HOME/Library/LaunchAgents/com.petpop.$unit.plist"
  sed -e "s#__REPO__#$REPO#g" -e "s#__GENAI__#$PETPOP_GENAI#g" -e "s#__MODELS__#$PETPOP_MODELS#g" \
      -e "s#__OLLAMA__#$OLLAMA_BIN#g" "$src" > "$dst"
  plutil -lint -s "$dst"
  launchctl bootout "gui/$(id -u)/com.petpop.$unit" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"
  echo "loaded com.petpop.$unit"
done

say "Done"
echo "Next: make -C mac models   (fetches ~20 GB of weights; every file must match pipelines/comfy/models.lock.json)"
echo "Then: make -C mac check && make -C mac tunnel"
