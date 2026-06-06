#!/usr/bin/env python3
"""Inject or update the library-digest MCP server entry in ~/.claude/settings.json.

Usage:  python configure_mcp.py <project_dir>
"""
import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: configure_mcp.py <project_dir>")

    project_dir = os.path.abspath(sys.argv[1])
    python_path = os.path.join(project_dir, ".venv", "bin", "python")
    server_path = os.path.join(project_dir, "server.py")

    if not os.path.exists(python_path):
        sys.exit(f"Virtual environment not found at {python_path}\nRun setup.sh first.")

    settings_path = os.path.expanduser("~/.claude/settings.json")

    # Read existing settings or start fresh
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError as e:
                sys.exit(f"Could not parse {settings_path}: {e}")
    else:
        settings = {}

    settings.setdefault("mcpServers", {})["library-digest"] = {
        "command": python_path,
        "args": [server_path],
    }

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print(f"Written to {settings_path}")


if __name__ == "__main__":
    main()
