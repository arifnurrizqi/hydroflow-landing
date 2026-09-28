#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/preflight.py
# --no-build and --pull never are intentional: no build/download on the ARM host.
docker compose up -d --no-build --pull never --wait --wait-timeout 120 cms
docker compose ps
