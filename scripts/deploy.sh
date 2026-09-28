#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/preflight.py
# --no-build and --pull never are intentional: no build/download on the ARM host.
# Recreate so Gunicorn loads updated read-only source files.
docker compose up -d --force-recreate --no-build --pull never --wait --wait-timeout 120 cms
docker compose ps
