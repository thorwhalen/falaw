"""Regenerate Claude SKILL.md from the falai tool registry.

Writes to two locations:
* `falai/data/skills/falai/SKILL.md` --- ships with the package.
* `.claude/skills/falai/SKILL.md` --- picked up by Claude Code in this repo.

Run after adding or modifying a tool:

    python misc/regenerate_skill.py
"""

from __future__ import annotations

import os

from falai.bridges.skill import write_skill_files

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    pkg_skill_dir = os.path.join(REPO_ROOT, "falai", "data", "skills", "falai")
    repo_skill_dir = os.path.join(REPO_ROOT, ".claude", "skills", "falai")
    for d in (pkg_skill_dir, repo_skill_dir):
        path = write_skill_files(d)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
