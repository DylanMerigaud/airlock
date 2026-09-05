#!/usr/bin/env bash
# The five checks a judge runs, in one command, the way README "Tests" lists them. Exits non-zero on the
# first failure. GitHub Actions is not used on this repository (billing), so this is the gate.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run pytest -q
uv run ruff check .
uv run pyright airlock agents airlock_mcp scripts
uv run python scripts/export_promql.py --check
(cd console && pnpm -s typecheck && pnpm -s lint)
echo "check.sh: all green"
