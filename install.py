#!/usr/bin/env python3
"""
install.py — Multi-agent installer for ThinkGraph.

Detects which agents are installed on this system and drops
adapters into the correct paths. Idempotent — safe to run multiple times.

Usage:
    python install.py              # auto-detect and install all
    python install.py --dry-run    # show what would be installed
    python install.py --agents opencode,codex  # install specific agents only
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Agent detection + path resolution
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.resolve()
ADAPTERS_DIR = SCRIPT_DIR / "adapters"


def get_home() -> Path:
    return Path.home()


def detect_agents() -> Dict[str, Path]:
    """Detect installed agents and return {name: adapter_source_path}."""
    detected: Dict[str, Path] = {}

    # OpenCode — project skill
    opencode_path = Path.cwd() / ".opencode" / "skills" / "thinkgraph" / "SKILL.md"
    if opencode_path.parent.parent.parent.exists() or _can_create(opencode_path):
        detected["opencode"] = ADAPTERS_DIR / "opencode" / "SKILL.md"

    # Claude Code — global skill (also auto-loaded by OpenCode)
    claude_path = get_home() / ".claude" / "skills" / "thinkgraph" / "SKILL.md"
    if claude_path.parent.parent.parent.exists() or _can_create(claude_path):
        detected["claude"] = ADAPTERS_DIR / "claude" / "SKILL.md"

    # Cursor — rules file
    cursor_path = Path.cwd() / ".cursor" / "rules" / "thinkgraph.mdc"
    if cursor_path.parent.parent.exists() or _can_create(cursor_path):
        detected["cursor"] = ADAPTERS_DIR / "cursor" / "thinkgraph.mdc"

    # Codex — AGENTS.md (check if exists or can append)
    agents_md = Path.cwd() / "AGENTS.md"
    if agents_md.exists() or _can_create(agents_md):
        detected["codex"] = ADAPTERS_DIR / "codex" / "AGENTS.md"

    # Copilot — .github/copilot-instructions.md
    copilot_path = Path.cwd() / ".github" / "copilot-instructions.md"
    if copilot_path.parent.exists() or _can_create(copilot_path):
        detected["copilot"] = ADAPTERS_DIR / "copilot" / "copilot-instructions.md"

    # Gemini CLI — GEMINI.md
    gemini_path = Path.cwd() / "GEMINI.md"
    if gemini_path.exists() or _can_create(gemini_path):
        detected["gemini"] = ADAPTERS_DIR / "gemini" / "GEMINI.md"

    return detected


def _can_create(path: Path) -> bool:
    """Check if we can create the parent directory."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def install_skill(source: Path, dest: Path, mode: str = "copy") -> bool:
    """Install a skill/adapter file. Returns True if changed."""
    if mode == "copy":
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_text(encoding="utf-8") == source.read_text(encoding="utf-8"):
            return False  # already up to date
        shutil.copy2(source, dest)
        return True
    return False


def install_append(source: Path, dest: Path, marker: str = "# thinkgraph") -> bool:
    """Append content to a file if not already present. Returns True if changed."""
    content = source.read_text(encoding="utf-8")
    if dest.exists():
        existing = dest.read_text(encoding="utf-8")
        if marker in existing:
            return False  # already installed
        dest.write_text(existing + "\n\n" + content, encoding="utf-8")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return True


def install_all(agents: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, bool]:
    """Install adapters for detected agents. Returns {agent: changed}."""
    detected = detect_agents()
    results: Dict[str, bool] = {}

    for name, source in detected.items():
        if agents and name not in agents:
            continue

        if name == "opencode":
            dest = Path.cwd() / ".opencode" / "skills" / "thinkgraph" / "SKILL.md"
            mode = "copy"
        elif name == "claude":
            dest = get_home() / ".claude" / "skills" / "thinkgraph" / "SKILL.md"
            mode = "copy"
        elif name == "cursor":
            dest = Path.cwd() / ".cursor" / "rules" / "thinkgraph.mdc"
            mode = "copy"
        elif name == "codex":
            dest = Path.cwd() / "AGENTS.md"
            mode = "append"
        elif name == "copilot":
            dest = Path.cwd() / ".github" / "copilot-instructions.md"
            mode = "append"
        elif name == "gemini":
            dest = Path.cwd() / "GEMINI.md"
            mode = "append"
        else:
            continue

        if dry_run:
            action = "copy" if mode == "copy" else "append"
            print(f"  [DRY RUN] {name}: {action} {source.name} -> {dest}")
            results[name] = False
        else:
            try:
                if mode == "copy":
                    changed = install_skill(source, dest)
                else:
                    changed = install_append(source, dest)
                results[name] = changed
                status = "installed" if changed else "up to date"
                print(f"  [{status}] {name}: {dest}")
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")
                results[name] = False

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="thinkgraph-install",
        description="Install ThinkGraph adapters for detected agents",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be installed without making changes",
    )
    parser.add_argument(
        "--agents", type=str, default=None,
        help="Comma-separated list of agents to install (default: all detected)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List detected agents and exit",
    )
    args = parser.parse_args()

    detected = detect_agents()

    if args.list:
        if detected:
            print("Detected agents:")
            for name in detected:
                print(f"  - {name}")
        else:
            print("No agents detected in current directory.")
        return

    agents = args.agents.split(",") if args.agents else None

    print(f"ThinkGraph installer - {'dry run' if args.dry_run else 'installing'}")
    print(f"Project: {Path.cwd()}")
    print()

    if not detected:
        print("No agents detected. Make sure you're in a project directory")
        print("with the expected agent config files (.opencode/, .cursor/, etc).")
        sys.exit(1)

    results = install_all(agents=agents, dry_run=args.dry_run)

    installed = sum(1 for v in results.values() if v)
    up_to_date = sum(1 for v in results.values() if not v)
    print()
    print(f"Done: {installed} installed, {up_to_date} up to date")

    if installed > 0 and not args.dry_run:
        print()
        print("Restart your agent for changes to take effect.")


if __name__ == "__main__":
    main()
