#!/usr/bin/env bash
# Sets up the Library Digest:
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

# ── Claude Code MCP config ────────────────────────────────────────────────
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "Register the MCP server in Claude Code?"
echo "  Settings file: $CLAUDE_SETTINGS"
printf "  [y/N] "
read -r REPLY
echo ""

REGISTERED_CLAUDE=false
if [[ "$REPLY" =~ ^[Yy]$ ]]; then
  "$PYTHON" "$SCRIPT_DIR/configure_mcp.py" "$SCRIPT_DIR"
  ok "MCP server 'library-digest' registered in Claude Code."
  REGISTERED_CLAUDE=true
else
  echo "Skipped. To register manually, add this to $CLAUDE_SETTINGS:"
  echo ""
  echo '  "mcpServers": {'
  echo '    "library-digest": {'
  echo "      \"command\": \"$PYTHON\","
  echo "      \"args\": [\"$SCRIPT_DIR/server.py\"]"
  echo '    }'
  echo '  }'
fi

# ── GitHub Copilot CLI MCP config ─────────────────────────────────────────
COPILOT_CONFIG="$HOME/.copilot/mcp-config.json"

echo ""
echo "Register the MCP server in GitHub Copilot CLI?"
echo "  Config file: $COPILOT_CONFIG"
printf "  [y/N] "
read -r REPLY
echo ""

REGISTERED_COPILOT=false
if [[ "$REPLY" =~ ^[Yy]$ ]]; then
  "$PYTHON" "$SCRIPT_DIR/configure_copilot.py" "$SCRIPT_DIR"
  ok "MCP server 'library-digest' registered in GitHub Copilot CLI."
  REGISTERED_COPILOT=true
else
  echo "Skipped. To register manually, add this to $COPILOT_CONFIG:"
  echo ""
  echo '  "mcpServers": {'
  echo '    "library-digest": {'
  echo "      \"type\": \"local\","
  echo "      \"command\": \"$PYTHON\","
  echo "      \"args\": [\"$SCRIPT_DIR/server.py\"],"
  echo '      "tools": ["*"]'
  echo '    }'
  echo '  }'
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "${bold}Done.${reset}"
echo ""
echo "Next steps:"
[[ "$REGISTERED_CLAUDE" == true ]]  && echo "  • Restart Claude Code to activate the new tools."
[[ "$REGISTERED_COPILOT" == true ]] && echo "  • Start a new Copilot CLI session to pick up the MCP server."
echo "  • Start the browser dashboard:  ${bold}./start.sh${reset}"
echo "  • Open:                         ${bold}http://localhost:8000${reset}"
echo ""
