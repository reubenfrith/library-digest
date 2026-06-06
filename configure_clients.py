#!/usr/bin/env python3
"""Interactively register library-digest as an MCP server across AI coding clients.

Usage:  python configure_clients.py <project_dir>
"""
import json
import os
import re
import sys


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    # Strip JSONC-style comments (// and /* … */) so Zed's settings.json parses cleanly
    raw = re.sub(r"//[^\n]*", "", raw)
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse {path}: {e}")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


# ── per-client registration ───────────────────────────────────────────────────

def register_claude(project_dir, python, server):
    path = os.path.expanduser("~/.claude/settings.json")
    cfg = _read_json(path)
    cfg.setdefault("mcpServers", {})["library-digest"] = {
        "command": python,
        "args": [server],
    }
    _write_json(path, cfg)
    return path


def register_copilot(project_dir, python, server):
    path = os.path.expanduser("~/.copilot/mcp-config.json")
    cfg = _read_json(path)
    cfg.setdefault("mcpServers", {})["library-digest"] = {
        "type": "local",
        "command": python,
        "args": [server],
        "tools": ["*"],
    }
    _write_json(path, cfg)
    return path


def register_opencode(project_dir, python, server):
    # opencode: command is an array; env key is "environment"; type is "local"
    path = os.path.expanduser("~/.config/opencode/opencode.json")
    cfg = _read_json(path)
    cfg.setdefault("mcp", {})["library-digest"] = {
        "type": "local",
        "command": [python, server],
        "enabled": True,
    }
    _write_json(path, cfg)
    return path


def register_cursor(project_dir, python, server):
    path = os.path.expanduser("~/.cursor/mcp.json")
    cfg = _read_json(path)
    cfg.setdefault("mcpServers", {})["library-digest"] = {
        "command": python,
        "args": [server],
    }
    _write_json(path, cfg)
    return path


def register_zed(project_dir, python, server):
    # Zed: "context_servers" key; "source": "custom" is required or entry is silently ignored
    path = os.path.expanduser("~/.config/zed/settings.json")
    cfg = _read_json(path)
    cfg.setdefault("context_servers", {})["library-digest"] = {
        "source": "custom",
        "command": python,
        "args": [server],
    }
    _write_json(path, cfg)
    return path


def register_goose(project_dir, python, server):
    # Goose uses YAML. Try PyYAML (often available transitively); fall back to guidance.
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "PyYAML not available in this venv.\n"
            "  Add manually to ~/.config/goose/config.yaml:\n\n"
            "  extensions:\n"
            "    library-digest:\n"
            "      bundled: false\n"
            "      enabled: true\n"
            "      name: library-digest\n"
            "      type: stdio\n"
            f"      cmd: {python}\n"
            f"      args: [{server}]\n"
            "      description: Library Digest research library\n"
            "      envs: {}\n"
        )

    path = os.path.expanduser("~/.config/goose/config.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    cfg.setdefault("extensions", {})["library-digest"] = {
        "bundled": False,
        "enabled": True,
        "name": "library-digest",
        "type": "stdio",
        "timeout": 300,
        "cmd": python,
        "args": [server],
        "description": "Library Digest — search and manage your research library",
        "envs": {},
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return path


def register_amp(project_dir, python, server):
    path = os.path.expanduser("~/.config/amp/settings.json")
    cfg = _read_json(path)
    cfg.setdefault("amp.mcpServers", {})["library-digest"] = {
        "command": python,
        "args": [server],
    }
    _write_json(path, cfg)
    return path


def register_continue(project_dir, python, server):
    # Continue: project-local .continue/mcpServers/ directory
    path = os.path.join(project_dir, ".continue", "mcpServers", "library-digest.json")
    cfg = _read_json(path)
    cfg.setdefault("mcpServers", {})["library-digest"] = {
        "command": python,
        "args": [server],
    }
    _write_json(path, cfg)
    return path


# ── client registry ───────────────────────────────────────────────────────────

CLIENTS = [
    ("Claude Code",          "~/.claude/settings.json",                         register_claude,   "Restart Claude Code to activate."),
    ("GitHub Copilot CLI",   "~/.copilot/mcp-config.json",                      register_copilot,  "Start a new Copilot CLI session."),
    ("opencode",             "~/.config/opencode/opencode.json",                 register_opencode, "Restart opencode to activate."),
    ("Cursor",               "~/.cursor/mcp.json",                               register_cursor,   "Restart Cursor to activate."),
    ("Zed",                  "~/.config/zed/settings.json",                      register_zed,      "Zed reloads settings automatically."),
    ("Goose",                "~/.config/goose/config.yaml",                      register_goose,    "Restart Goose to activate."),
    ("Amp",                  "~/.config/amp/settings.json",                      register_amp,      "Restart Amp to activate."),
    ("Continue (project)",   ".continue/mcpServers/library-digest.json",         register_continue, "Works in Continue agent mode; commit the file to share with your team."),
]


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    project_dir = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    python = os.path.join(project_dir, ".venv", "bin", "python")
    server = os.path.join(project_dir, "server.py")

    if not os.path.exists(python):
        sys.exit(f"Virtual environment not found at {python}\nRun setup.sh first.")

    print()
    print("Which AI clients would you like to register?")
    print()
    for i, (name, cfg_path, _, _) in enumerate(CLIENTS, 1):
        print(f"  {i}) {name:<25} {cfg_path}")
    print()
    print("Enter numbers separated by spaces, 'a' for all, or Enter to skip:")
    print()

    try:
        response = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nSkipped.")
        return

    if not response:
        print("Skipped.")
        return

    if response.lower() in ("a", "all"):
        selected = list(range(len(CLIENTS)))
    else:
        selected = []
        for part in response.split():
            try:
                idx = int(part) - 1
                if 0 <= idx < len(CLIENTS):
                    selected.append(idx)
            except ValueError:
                pass

    if not selected:
        print("No valid selection. Skipped.")
        return

    green = "\033[32m"; yellow = "\033[33m"; reset = "\033[0m"
    print()
    notes = []
    for idx in selected:
        name, _, fn, note = CLIENTS[idx]
        try:
            written = fn(project_dir, python, server)
            print(f"  {green}✓{reset} {name:<25} → {written}")
            notes.append(f"  • {name}: {note}")
        except RuntimeError as e:
            first_line = str(e).split("\n")[0]
            print(f"  {yellow}!{reset} {name:<25} — {first_line}")
        except Exception as e:
            print(f"  {yellow}!{reset} {name:<25} — {e}")

    if notes:
        print()
        print("Next steps:")
        for n in notes:
            print(n)
    print()


if __name__ == "__main__":
    main()
