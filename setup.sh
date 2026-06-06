#!/usr/bin/env bash
# Sets up the Library Digest:
#   1. Installs Python dependencies via uv sync
#   2. Optionally registers the MCP server with one or more AI clients

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"

# ── colours ──────────────────────────────────────────────────────────────
bold=$'\e[1m'; reset=$'\e[0m'; green=$'\e[32m'; yellow=$'\e[33m'; red=$'\e[31m'
ok()   { echo "${green}✓${reset} $*"; }
warn() { echo "${yellow}!${reset} $*"; }
die()  { echo "${red}✗${reset} $*" >&2; exit 1; }

echo ""
echo "${bold}Library Digest — setup${reset}"
echo "─────────────────────────────────────────"

# ── uv check ─────────────────────────────────────────────────────────────
command -v uv &>/dev/null || die "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"

# ── Dependencies ──────────────────────────────────────────────────────────
echo "Installing dependencies (this may take a minute on first run)…"
cd "$SCRIPT_DIR"
uv sync --quiet
ok "Dependencies installed."

# ── Database init ─────────────────────────────────────────────────────────
echo "Initialising database…"
"$PYTHON" -c "import sys; sys.path.insert(0, '${SCRIPT_DIR}'); import db; db.init_db()"
ok "Database ready."

# ── Embedding model pre-warm ──────────────────────────────────────────────
echo "Pre-loading embedding model (downloads ~80 MB on first run)…"
"$PYTHON" - <<'PYEOF'
from chromadb.utils import embedding_functions
embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
PYEOF
ok "Embedding model ready."

# ── MCP client registration ───────────────────────────────────────────────
"$PYTHON" "$SCRIPT_DIR/configure_clients.py" "$SCRIPT_DIR"

# ── Done ──────────────────────────────────────────────────────────────────
echo "${bold}Done.${reset}"
echo ""
echo "  Start the browser dashboard:  ${bold}./start.sh${reset}"
echo "  Open:                         ${bold}http://localhost:8000${reset}"
echo ""
