#!/usr/bin/env python3
"""Register library-digest as a user-scope MCP server with Claude Code.

Usage:  python configure_mcp.py <project_dir>

Uses the official `claude mcp add -s user` CLI so we never have to hand-edit
~/.claude.json (which holds the user's OAuth session and lots of other state).
User scope makes the server available from every project, not just this one.
"""
import os
import shutil
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: configure_mcp.py <project_dir>")

    project_dir = os.path.abspath(sys.argv[1])
    python_path = os.path.join(project_dir, ".venv", "bin", "python")
    server_path = os.path.join(project_dir, "server.py")

    if not os.path.exists(python_path):
        sys.exit(f"Virtual environment not found at {python_path}\nRun setup.sh first.")

    if shutil.which("claude") is None:
        sys.exit("`claude` CLI not found on PATH. Install Claude Code first: "
                 "https://docs.claude.com/en/docs/claude-code/quickstart")

    # Remove any prior entry so the add is idempotent; ignore failure (no entry yet).
    subprocess.run(
        ["claude", "mcp", "remove", "-s", "user", "library-digest"],
        capture_output=True, check=False,
    )

    result = subprocess.run(
        ["claude", "mcp", "add", "-s", "user", "library-digest",
         "--", python_path, server_path],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.exit(result.stderr.strip() or result.stdout.strip()
                 or "`claude mcp add` failed")

    print(f"Registered library-digest at user scope (~/.claude.json).")
    print("Run `claude mcp list` to verify, then restart any open Claude Code sessions.")


if __name__ == "__main__":
    main()
