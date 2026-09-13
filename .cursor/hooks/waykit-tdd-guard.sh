#!/usr/bin/env bash
set -euo pipefail
if [ -x "$HOME/.agents/bin/kit" ]; then
  exec "$HOME/.agents/bin/kit" tdd-guard
fi
if command -v wk >/dev/null 2>&1; then
  exec wk tdd-guard
fi
printf '%s\n' '{"permission":"allow","additional_context":"Waykit TDD Guard skipped: wk not on PATH"}'
