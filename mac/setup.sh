#!/usr/bin/env bash
# PetPop GenAI host setup for an Apple Silicon Mac (profile mac-m4pro). Idempotent; re-run after a git pull.
#
#   cd nv-petpop && mac/setup.sh
#
# Installs (Homebrew): python@3.11, git, git-lfs, uv, ollama, caddy, cloudflared.
# Clones at the commits pinned in pipelines/comfy/requirements.txt:
#   ComfyUI (+ ComfyUI_IPAdapter_plus)      -> $PETPOP_GENAI/ComfyUI       (venv: ComfyUI/venv)
#   hunyuan3d-2.1-mac (MPS fork)            -> $PETPOP_GENAI/hunyuan3d-2.1-mac (venv: its own, from install.sh)
# Then: pulls the Ollama model, writes $PETPOP_GENAI/genai.env (GENAI_TOKEN etc.), renders and loads the three
# launchd units (com.petpop.comfyui, com.petpop.shape, com.petpop.ollama). Weights: `make -C mac models`.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PETPOP_GENAI="${PETPOP_GENAI:-$HOME/petpop-genai}"
PETPOP_MODELS="${PETPOP_MODELS:-$HOME/petpop-models}"
PINS="$REPO/pipelines/comfy/requirements.txt"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
pin() { awk -v n="$1" '$1==n {print $2" "$3}' "$PINS"; }

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "mac/setup.sh is for Apple Silicon macOS"; exit 1; }
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
mkdir -p "$PETPOP_GENAI/logs" "$PETPOP_MODELS"

say "Homebrew packages"
brew install python@3.11 git git-lfs uv ollama caddy cloudflared

clone_at() {  # clone_at name dir
  read -r url commit < <(pin "$1")
  [ -d "$2/.git" ] || git clone --quiet "$url" "$2"
  git -C "$2" fetch --quiet origin "$commit" 2>/dev/null || git -C "$2" fetch --quiet origin
  git -C "$2" checkout --quiet "$commit"
  echo "$1 @ $commit"
}

say "ComfyUI (MPS)"
clone_at ComfyUI "$PETPOP_GENAI/ComfyUI"
[ -d "$PETPOP_GENAI/ComfyUI/venv" ] || uv venv --python 3.11 "$PETPOP_GENAI/ComfyUI/venv"
VIRTUAL_ENV="$PETPOP_GENAI/ComfyUI/venv" uv pip install --python "$PETPOP_GENAI/ComfyUI/venv/bin/python" torch torchvision torchaudio
VIRTUAL_ENV="$PETPOP_GENAI/ComfyUI/venv" uv pip install --python "$PETPOP_GENAI/ComfyUI/venv/bin/python" -r "$PETPOP_GENAI/ComfyUI/requirements.txt"
clone_at ComfyUI_IPAdapter_plus "$PETPOP_GENAI/ComfyUI/custom_nodes/ComfyUI_IPAdapter_plus"
sed "s#__MODELS__#$PETPOP_MODELS#g" "$REPO/mac/comfy_extra_model_paths.yaml.in" > "$PETPOP_GENAI/ComfyUI/extra_model_paths.yaml"
mkdir -p "$PETPOP_MODELS"/{checkpoints,vae,controlnet,ipadapter,clip_vision,loras,diffusion_models,hf}

say "Hunyuan3D-2.1 MPS fork (shape only)"
clone_at hunyuan3d-2.1-mac "$PETPOP_GENAI/hunyuan3d-2.1-mac"
( cd "$PETPOP_GENAI/hunyuan3d-2.1-mac" && chmod +x install.sh && ./install.sh --shape-only --skip-weights )
"$PETPOP_GENAI/hunyuan3d-2.1-mac/venv/bin/python" -m pip install -q -r "$REPO/mac/shape_server/requirements.txt"

say "Ollama"
brew services stop ollama >/dev/null 2>&1 || true   # launchd unit below owns it
OLLAMA_HOST=127.0.0.1:11434 ollama serve >/dev/null 2>&1 & OLLAMA_PID=$!
sleep 3
ollama pull qwen2.5:7b-instruct-q4_K_M
kill "$OLLAMA_PID" 2>/dev/null || true

say "Secrets ($PETPOP_GENAI/genai.env)"
if [ ! -f "$PETPOP_GENAI/genai.env" ]; then
  umask 077
  cat > "$PETPOP_GENAI/genai.env" <<ENV
GENAI_PROFILE=mac-m4pro
GENAI_TOKEN=$(openssl rand -hex 24)
PETPOP_MODELS=$PETPOP_MODELS
HY3D_DIR=$PETPOP_GENAI/hunyuan3d-2.1-mac
PETPOP_PROXY_PORT=8787
ENV
fi
echo "GENAI_TOKEN is in $PETPOP_GENAI/genai.env (chmod 600)"

say "launchd units"
mkdir -p "$HOME/Library/LaunchAgents"
for unit in comfyui shape ollama; do
  src="$REPO/mac/launchd/com.petpop.$unit.plist.in"
  dst="$HOME/Library/LaunchAgents/com.petpop.$unit.plist"
  sed -e "s#__REPO__#$REPO#g" -e "s#__GENAI__#$PETPOP_GENAI#g" -e "s#__MODELS__#$PETPOP_MODELS#g" \
      -e "s#__OLLAMA__#$(command -v ollama)#g" "$src" > "$dst"
  launchctl bootout "gui/$(id -u)/com.petpop.$unit" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$dst"
  echo "loaded com.petpop.$unit"
done

say "Done"
echo "Next: make -C mac models   (downloads ~25 GB and writes SHA256 pins into pipelines/comfy/models.yaml)"
echo "Then: make -C mac check && mac/tunnel.sh"
