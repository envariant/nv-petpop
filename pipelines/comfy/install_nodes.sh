#!/usr/bin/env bash
# install_nodes.sh requirements.txt custom_nodes_dir host : clone each node pack for `host` at its pinned commit.
set -euo pipefail
host="${3:-nvidia-24gb}"
grep -vE '^\s*(#|$)' "$1" | while read -r name repo commit hosts; do
  [ "$name" = "ComfyUI" ] && continue
  case ",$hosts," in *",$host,"*) ;; *) continue ;; esac
  case "$repo" in *ComfyUI*|*comfyui*) ;; *) continue ;; esac
  [ -d "$2/$name" ] || git clone --quiet "$repo" "$2/$name"
  git -C "$2/$name" fetch --quiet origin "$commit" 2>/dev/null || true
  git -C "$2/$name" checkout --quiet "$commit"
  [ -f "$2/$name/requirements.txt" ] && pip3 install --no-cache-dir -r "$2/$name/requirements.txt"
done
