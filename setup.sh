#!/usr/bin/env bash
# Sets up the Course Explorer:
#   1. Installs Python dependencies via uv sync
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

# ── uv check ─────────────────────────────────────────────────────────────
command -v uv &>/dev/null || die "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"

# ── Dependencies ──────────────────────────────────────────────────────────
echo "Installing dependencies (this may take a minute on first run)…"
cd "$SCRIPT_DIR"
uv sync --quiet
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
