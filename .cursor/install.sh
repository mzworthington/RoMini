#!/usr/bin/env bash
# Idempotent environment bootstrap for RoMini.
# Safe to run repeatedly and on either the stock image or a prebuilt snapshot.
set -euo pipefail

# The stock image ships Python but not the venv bootstrap module. Install it
# only when it's missing (a no-op when it's already baked into the base image).
if ! python3 -c 'import ensurepip' >/dev/null 2>&1; then
  echo "python3 venv module missing; installing python3-venv..."
  sudo apt-get update
  sudo apt-get install -y "python3-venv"
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e . --no-deps

echo "RoMini environment ready."
