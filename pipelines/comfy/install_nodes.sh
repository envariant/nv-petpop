#!/usr/bin/env bash
# install_nodes.sh requirements.txt custom_nodes_dir : clone each pack at its pinned commit.
set -euo pipefail
grep -vE '^\s*(#|$)' "$1" | while read -r name repo commit; do
  if [ "$commit" = "REPLACE_WITH_COMMIT" ]; then echo "unpinned node pack $name" >&2; exit 1; fi
  git clone "$repo" "$2/$name" && git -C "$2/$name" checkout "$commit"
  [ -f "$2/$name/requirements.txt" ] && pip3 install --no-cache-dir -r "$2/$name/requirements.txt"
done
