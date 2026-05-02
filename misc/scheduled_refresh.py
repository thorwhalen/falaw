"""Orchestration script for the scheduled fal.ai docs refresh.

Designed to be invoked by a remote scheduled agent that has a fresh checkout
of the repo. Behavior:

1. Set ``FALAW_DATA_DIR`` to ``misc/falaw_state`` (in-repo) so any journal
   entries written during the run get committed alongside doc changes.
2. Cheap watch: ``refresh_llms()``. If nothing changed, exit with a clean
   summary --- the scheduled agent should then make no commit.
3. If ``llms-full.txt`` changed, run ``refresh_full_docs()`` to re-crawl
   per-page docs and rebuild ``misc/docs/fal_ai_docs_full.md``.
4. Print a JSON summary to stdout so the agent can decide whether to
   commit / open a PR.

Exits 0 on success regardless of "changed or not"; non-zero only on an
unexpected error. Use ``git status --porcelain`` to decide whether there
is anything to commit.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = REPO / "misc" / "falaw_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FALAW_DATA_DIR", str(STATE_DIR))

from falaw.refresh import refresh_full_docs, refresh_llms  # noqa: E402


def main() -> int:
    summary: dict = {"llms": refresh_llms()}
    llms_full_changed = summary["llms"].get("llms-full", {}).get("changed", False)
    if llms_full_changed:
        # llms_full just changed; bypass the staleness gate (refresh_llms
        # already saved the new ETag, so the gate would now report fresh).
        summary["full_docs"] = refresh_full_docs(force=True)
    json.dump(summary, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
