#!/usr/bin/env bash
# Sets up the Course Explorer:
#   1. Creates .venv and installs Python dependencies
#   2. Optionally registers the MCP server in ~/.claude/settings.json

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
echo "${bold}Course Explorer — setup${reset}"
echo "─────────────────────────────────────────"

# ── Python version check ──────────────────────────────────────────────────
PY=$(command -v python3 || command -v python || die "Python 3.9+ required but not found.")
PY_VER=$("$PY" -c "import sys; print(sys.version_info[:2])")
[[ "$PY_VER" < "(3, 9)" ]] && die "Python 3.9+ required (found $PY_VER)."

# ── Virtual environment ───────────────────────────────────────────────────
if [[ -d "$VENV" ]]; then
  ok "Virtual environment already exists — skipping creation."
else
  echo "Creating virtual environment…"
  "$PY" -m venv "$VENV"
  ok "Virtual environment created at .venv/"
fi

# ── Dependencies ──────────────────────────────────────────────────────────
echo "Installing dependencies (this may take a minute on first run)…"
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "$SCRIPT_DIR/requirements.txt"
ok "Dependencies installed."

# ── Embedding model pre-warm ──────────────────────────────────────────────
echo "Pre-loading embedding model (downloads ~80 MB on first run)…"
"$PYTHON" - <<'PYEOF'
from chromadb.utils import embedding_functions
embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
PYEOF
ok "Embedding model ready."

# ── MCP server config ─────────────────────────────────────────────────────
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "Register the MCP server in Claude Code?"
echo "  Settings file: $SETTINGS"
printf "  [y/N] "
read -r REPLY
echo ""

if [[ "$REPLY" =~ ^[Yy]$ ]]; then
  "$PYTHON" "$SCRIPT_DIR/configure_mcp.py" "$SCRIPT_DIR"
  ok "MCP server 'course-explorer' registered."
  warn "Restart Claude Code to activate the new tools."
else
  echo "Skipped. To register manually, add this to $SETTINGS:"
  echo ""
  echo '  "mcpServers": {'
  echo '    "course-explorer": {'
  echo "      \"command\": \"$PYTHON\","
  echo "      \"args\": [\"$SCRIPT_DIR/server.py\"]"
  echo '    }'
  echo '  }'
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "${bold}Done.${reset}"
echo ""
echo "Next steps:"
echo "  • Restart Claude Code if you registered the MCP server."
echo "  • Start the browser dashboard:  ${bold}./start.sh${reset}"
echo "  • Open:                         ${bold}http://localhost:8000${reset}"
echo ""
