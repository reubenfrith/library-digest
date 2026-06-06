#!/usr/bin/env bash
# Start the Library Digest browser dashboard at http://localhost:8000

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

PORT="${PORT:-8000}"

echo "Starting Library Digest dashboard on http://localhost:${PORT}"
echo "Press Ctrl+C to stop."
echo ""

cd "$SCRIPT_DIR"
exec "$PYTHON" -m uvicorn api:app --port "$PORT" --reload
