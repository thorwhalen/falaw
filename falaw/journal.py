"""Agent journal: append-only log of notes, issues and improvements.

Why this exists: agents (and falaw itself) leave traces here whenever
something is harder than expected, surprising, or worth remembering. The
Claude skill teaches future sessions to read recent entries before doing
novel work, so each session starts smarter than the last.

Usage:

    >>> from falaw import journal
    >>> journal.note("schnell tier returns 1024x1024 by default")  # doctest: +SKIP
    >>> journal.issue("FLUX dev refused a benign prompt as NSFW",
    ...               suggestion="Try guidance_scale=2.0")  # doctest: +SKIP
    >>> journal.improvement("Add an `upscale_image` wrapper for clarity-upscaler",
    ...                     tags=("backlog",))  # doctest: +SKIP
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Iterable, Iterator, Literal, Optional

EntryKind = Literal["note", "issue", "improvement", "trace"]


def _default_journal_dir() -> str:
    base = os.environ.get("FALAW_DATA_DIR") or os.path.expanduser("~/.config/falaw")
    return os.path.join(base, "journal")


@dataclass(frozen=True, slots=True, kw_only=True)
class JournalEntry:
    id: str
    timestamp: float
    kind: EntryKind
    text: str
    tags: tuple[str, ...] = ()
    suggestion: str = ""
    context: dict = field(default_factory=dict)


class Journal:
    """File-backed append-only journal.

    Each entry becomes a single JSON file. Names are timestamp-prefixed so
    `sorted(os.listdir(...))` yields chronological order without parsing.

    >>> import tempfile
    >>> j = Journal(tempfile.mkdtemp())
    >>> _ = j.append(kind="note", text="hello")
    >>> _ = j.append(kind="issue", text="boom", suggestion="try X")
    >>> [e.kind for e in j]
    ['note', 'issue']
    """

    def __init__(self, directory: Optional[str] = None):
        self.directory = directory or _default_journal_dir()
        os.makedirs(self.directory, exist_ok=True)

    def append(
        self,
        *,
        kind: EntryKind,
        text: str,
        tags: Iterable[str] = (),
        suggestion: str = "",
        context: Optional[dict] = None,
    ) -> JournalEntry:
        entry = JournalEntry(
            id=uuid.uuid4().hex[:12],
            timestamp=time.time(),
            kind=kind,
            text=text,
            tags=tuple(tags),
            suggestion=suggestion,
            context=dict(context or {}),
        )
        fname = f"{int(entry.timestamp * 1000):014d}-{entry.id}.json"
        path = os.path.join(self.directory, fname)
        with open(path, "w") as f:
            json.dump(asdict(entry), f, indent=2, default=str)
        return entry

    def __iter__(self) -> Iterator[JournalEntry]:
        for name in sorted(os.listdir(self.directory)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self.directory, name)) as f:
                data = json.load(f)
            data["tags"] = tuple(data.get("tags") or ())
            yield JournalEntry(**data)

    def recent(self, n: int = 20) -> list[JournalEntry]:
        return list(self)[-n:]

    def filter(
        self,
        *,
        kind: Optional[EntryKind] = None,
        tag: Optional[str] = None,
    ) -> list[JournalEntry]:
        return [
            e
            for e in self
            if (kind is None or e.kind == kind)
            and (tag is None or tag in e.tags)
        ]


@lru_cache(maxsize=1)
def _default_journal() -> Journal:
    return Journal()


def note(text: str, **kw) -> JournalEntry:
    return _default_journal().append(kind="note", text=text, **kw)


def issue(text: str, **kw) -> JournalEntry:
    return _default_journal().append(kind="issue", text=text, **kw)


def improvement(text: str, **kw) -> JournalEntry:
    return _default_journal().append(kind="improvement", text=text, **kw)


def recent(n: int = 20) -> list[JournalEntry]:
    return _default_journal().recent(n)
