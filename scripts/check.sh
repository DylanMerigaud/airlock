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

# The test count is quoted in prose (docs/DEVPOST.md) and it drifted three times in three panel
# passes on 2026-09-05 because nothing checked it. This does.
collected=$(uv run pytest -q --collect-only 2>&1 | grep -o '^[0-9]* tests\? collected' | grep -o '^[0-9]*')
claimed=$(grep -o '[0-9]\+ tests, none of them calls a model' docs/DEVPOST.md | grep -o '^[0-9]*')
if [ "$collected" != "$claimed" ]; then
  echo "docs/DEVPOST.md claims ${claimed} tests, uv run pytest collects ${collected}: update the sentence in docs/DEVPOST.md" >&2
  exit 1
fi

echo "check.sh: all green"
