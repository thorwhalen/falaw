"""CLI entry: ``python -m falaw <command>``.

Commands:
  refresh-llms          Conditional GET of llms.txt and llms-full.txt.
  refresh-full          Re-crawl per-page docs (gated on llms-full staleness).
  state                 Print the saved refresh state (etags, last fetch).
  regen-skill           Regenerate the Claude SKILL.md from the registry.
"""

from __future__ import annotations

import json
import sys

from .bridges.skill import write_skill_files
from .refresh import refresh_full_docs, refresh_llms, refresh_state


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, *rest = argv
    if cmd == "refresh-llms":
        _print_json(refresh_llms())
        return 0
    if cmd == "refresh-full":
        force = "--force" in rest
        _print_json(refresh_full_docs(force=force))
        return 0
    if cmd == "state":
        _print_json(refresh_state())
        return 0
    if cmd == "regen-skill":
        import os

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for d in (
            os.path.join(repo_root, "falaw", "data", "skills", "falaw"),
            os.path.join(repo_root, ".claude", "skills", "falaw"),
        ):
            print("wrote", write_skill_files(d))
        return 0
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
