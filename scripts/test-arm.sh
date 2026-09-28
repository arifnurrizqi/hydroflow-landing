#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker run --rm --network none --memory 256m --memory-swap 256m \
  --cpus 0.5 --pids-limit 32 --read-only --tmpfs /tmp:size=24m,mode=1777 \
  --mount "type=bind,src=$PWD,dst=/workspace,readonly" --workdir /workspace \
  --entrypoint python hydroflow-landing-cms-cms:latest \
  scripts/check_tests.py
