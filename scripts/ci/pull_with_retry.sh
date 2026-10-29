#!/usr/bin/env bash
# Pull container images with retries (docs/42 §7.2): registries rate-limit concurrent pulls of the
# same image (seen: cgr.dev "toomanyrequests" when the push and PR runs started together).
set -euo pipefail
for image in "$@"; do
  for attempt in 1 2 3 4 5; do
    if docker pull -q "$image"; then
      break
    fi
    if [ "$attempt" = 5 ]; then
      echo "::error::could not pull $image after $attempt attempts"
      exit 1
    fi
    delay=$((attempt * 15 + RANDOM % 10))
    echo "pull of $image failed (attempt $attempt), retrying in ${delay}s"
    sleep "$delay"
  done
done
