"""Result wrapper: parse fal responses into typed assets, lazy download."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True, slots=True)
class Asset:
    """A single piece of generated media.

    Holds the URL plus minimal typed metadata. `download` materializes it.
    """

    url: str
    kind: str  # "image" | "video" | "audio" | "other"
    content_type: str = ""
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    metadata: dict = field(default_factory=dict)

    def download(self, *, to: Optional[str] = None) -> str:
        """Download the asset to a file. Returns the local path."""
        import urllib.request

        if to is None:
            to = os.path.join(
                os.getcwd(),
                f"pyfal_asset_{abs(hash(self.url)) % 10**8}{self._infer_extension()}",
            )
        parent = os.path.dirname(os.path.abspath(to))
        if parent:
            os.makedirs(parent, exist_ok=True)
        urllib.request.urlretrieve(self.url, to)
        return to

    def _infer_extension(self) -> str:
        if self.content_type:
            ext = mimetypes.guess_extension(self.content_type) or ""
            if ext:
                return ext
        return {"image": ".png", "video": ".mp4", "audio": ".mp3"}.get(
            self.kind, ".bin"
        )


@dataclass(slots=True)
class Result:
    """A fal call result with parsed assets and the original raw response.

    The raw response is kept so callers can inspect provider-specific fields
    (timings, seed, has_nsfw_concepts, ...) that we do not normalize.
    """

    assets: list[Asset] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    application: str = ""
    arguments: dict = field(default_factory=dict)

    @property
    def first(self) -> Optional[Asset]:
        return self.assets[0] if self.assets else None

    def download_all(self, *, to_dir: Optional[str] = None) -> list[str]:
        to_dir = to_dir or os.getcwd()
        os.makedirs(to_dir, exist_ok=True)
        paths: list[str] = []
        stem_base = self.application.replace("/", "_") or "asset"
        for i, a in enumerate(self.assets):
            path = os.path.join(to_dir, f"{stem_base}_{i}{a._infer_extension()}")
            paths.append(a.download(to=path))
        return paths


# response shape -> (key in raw response, asset kind)
_KIND_KEYS = (
    ("images", "image"),
    ("image", "image"),
    ("videos", "video"),
    ("video", "video"),
    ("audios", "audio"),
    ("audio", "audio"),
    ("audio_url", "audio"),
)


def parse_response(
    raw: dict,
    *,
    application: str,
    arguments: dict,
) -> Result:
    """Best-effort parser over the common fal response shapes.

    fal models return a variety of layouts (lists, single objects, bare URLs).
    We normalize each into Asset(url, kind, ...). Unknown shapes pass through
    as `raw` only --- callers can read `result.raw` for anything we miss.
    """
    assets: list[Asset] = []
    if isinstance(raw, dict):
        for key, kind in _KIND_KEYS:
            val = raw.get(key)
            if val is None:
                continue
            for item in val if isinstance(val, list) else [val]:
                assets.append(_to_asset(item, kind))
    return Result(
        assets=assets,
        raw=raw if isinstance(raw, dict) else {},
        application=application,
        arguments=dict(arguments),
    )


def _to_asset(item: Any, kind: str) -> Asset:
    if isinstance(item, str):
        return Asset(url=item, kind=kind)
    if isinstance(item, dict):
        return Asset(
            url=item.get("url", ""),
            kind=kind,
            content_type=item.get("content_type", ""),
            width=int(item.get("width") or 0),
            height=int(item.get("height") or 0),
            duration_s=float(item.get("duration") or 0),
            metadata={
                k: v
                for k, v in item.items()
                if k not in {"url", "content_type", "width", "height", "duration"}
            },
        )
    return Asset(url=str(item), kind=kind)
