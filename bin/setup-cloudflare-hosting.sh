#!/usr/bin/env bash
# Thin product-repo shim — runs the canonical bootstrap from edge-dns.
# Copy this file to your product repo as `bin/setup-cloudflare-hosting.sh`.
#
# Override the ref when pinning:
#   EDGE_DNS_REF=<sha> bin/setup-cloudflare-hosting.sh
set -euo pipefail

EDGE_DNS_REF="${EDGE_DNS_REF:-main}"
SCRIPT_URL="https://raw.githubusercontent.com/mzworthington/edge-dns/${EDGE_DNS_REF}/scripts/setup-cloudflare-hosting.sh"

export PRODUCT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PRODUCT_ROOT"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL "$SCRIPT_URL" -o "${tmpdir}/setup-cloudflare-hosting.sh"
bash "${tmpdir}/setup-cloudflare-hosting.sh" "$@"
