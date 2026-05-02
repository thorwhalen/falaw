"""Regenerate Claude SKILL.md from the falaw tool registry.

Writes to two locations:
* `falaw/data/skills/falaw/SKILL.md` --- ships with the package.
* `.claude/skills/falaw/SKILL.md` --- picked up by Claude Code in this repo.

Run after adding or modifying a tool:

    python misc/regenerate_skill.py
"""

from __future__ import annotations

import os

from falaw.bridges.skill import write_skill_files

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    pkg_skill_dir = os.path.join(REPO_ROOT, "falaw", "data", "skills", "falaw")
    repo_skill_dir = os.path.join(REPO_ROOT, ".claude", "skills", "falaw")
    for d in (pkg_skill_dir, repo_skill_dir):
        path = write_skill_files(d)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
