#!/usr/bin/env python3
"""Inject or update the library-digest MCP server entry in ~/.copilot/mcp-config.json.

Usage:  python configure_copilot.py <project_dir>
"""
import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: configure_copilot.py <project_dir>")

    project_dir = os.path.abspath(sys.argv[1])
    python_path = os.path.join(project_dir, ".venv", "bin", "python")
    server_path = os.path.join(project_dir, "server.py")

    if not os.path.exists(python_path):
        sys.exit(f"Virtual environment not found at {python_path}\nRun setup.sh first.")

    config_path = os.path.expanduser("~/.copilot/mcp-config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as e:
                sys.exit(f"Could not parse {config_path}: {e}")
    else:
        config = {}

    config.setdefault("mcpServers", {})["library-digest"] = {
        "type": "local",
        "command": python_path,
        "args": [server_path],
        "tools": ["*"],
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print(f"Written to {config_path}")


if __name__ == "__main__":
    main()
