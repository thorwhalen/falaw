"""Cost estimation: ModelRecord.cost_estimate + Scene rollups.

Two surfaces here:

- :func:`estimate_call_cost(record, *, count=1, seconds=None, megapixels=None,
  tokens=None)` — turn one model's :class:`CostEstimate` into a USD figure.
- :func:`estimate_scene_cost(scene, *, ...)` — walk every Shot + Beat in a
  :class:`falaw.Scene` and sum the per-call costs that
  :func:`falaw.render_scene` would incur. Returns a structured rollup
  (per-line + totals) so UIs can show "this render would cost ~$0.42".

A scene-level estimate is *advisory*. It's based on the same
``pick_model(category, quality_tier=...)`` lookup that the renderer
uses, multiplied by per-line duration / pixel budgets. Real costs vary
with model fluctuations and provider billing rules, but this is good
enough to gate on (e.g. ``--budget=1.00``) and to surface in
``muvid status``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .base import CostEstimate, ModelRecord
from .registry import pick_model
from .scene import Beat, Scene, Shot


@dataclass(frozen=True, slots=True, kw_only=True)
class CostLine:
    """One line item in a scene rollup."""

    kind: str  # "shot.image" | "shot.video" | "beat.tts" | "beat.avatar" | ...
    item_id: str  # shot.id or beat.id
    model_id: str
    amount: float
    currency: str
    note: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CostRollup:
    """Result of :func:`estimate_scene_cost`."""

    total_amount: float
    currency: str = "USD"
    lines: tuple[CostLine, ...] = ()
    skipped: tuple[str, ...] = ()  # human-readable notes for entries we couldn't price

    def by_kind(self) -> dict[str, float]:
        """Sum per ``kind`` for quick inspection."""
        out: dict[str, float] = {}
        for ln in self.lines:
            out[ln.kind] = out.get(ln.kind, 0.0) + ln.amount
        return out


def estimate_call_cost(
    record: ModelRecord,
    *,
    count: int = 1,
    seconds: float | None = None,
    megapixels: float | None = None,
    tokens: int | None = None,
) -> Optional[float]:
    """Cost of one fal call against ``record``.

    Returns ``None`` when the cost is **unknown**, so callers can
    distinguish "free" from "we can't say". That happens when the record
    carries no ``cost_estimate`` at all, or when its pricing is
    quantity-based (``per_second`` / ``per_token``) and the caller did
    not supply the quantity — an unpriceable call, not a free one.

    Returning ``0.0`` for a missing quantity would be actively dangerous:
    a ``per_second`` clip is the single most expensive thing fal bills
    for, and a caller gating a budget on the answer would read
    "$0.00" and spend real money without a prompt. ``None`` instead
    propagates to ``CallPlan.estimated_cost_usd`` and lights up
    ``Plan.has_unknown_costs``, which exists for exactly this case.
    Callers that know the quantity should pass it; ``per_second`` callers
    can fall back to ``record.max_clip_seconds`` for an upper bound.

    ``per_megapixel`` is deliberately different: an image's pixel budget
    has a sane house default (below), so it stays priceable.
    """
    ce: CostEstimate | None = record.cost_estimate
    if ce is None:
        return None
    if ce.kind == "per_call":
        return ce.amount * count
    if ce.kind == "per_image":
        return ce.amount * count
    if ce.kind == "per_second":
        if seconds is None:
            return None  # unknown duration → unpriceable, NOT free
        return ce.amount * seconds * count
    if ce.kind == "per_megapixel":
        # Default to a 16:9 1024-wide canvas if the caller didn't say
        # (≈0.59 MP); enough to give a useful upper-bound estimate.
        mp = megapixels if megapixels is not None else 0.6
        return ce.amount * mp * count
    if ce.kind == "per_token":
        if tokens is None:
            return None  # unknown token count → unpriceable, NOT free
        return ce.amount * tokens * count
    return None


def _shot_pricing_lines(
    shot: Shot,
    *,
    style: str,
    shots_as_video: bool,
    quality: str,
    skipped: list[str],
) -> list[CostLine]:
    out: list[CostLine] = []
    duration = float(getattr(shot, "duration_s", 0.0) or 0.0)

    img_record = pick_model(category="image", quality_tier=quality)
    img_cost = estimate_call_cost(img_record)
    if img_cost is None:
        skipped.append(
            f"shot {shot.id} image gen: no cost_estimate on {img_record.id!r}"
        )
    else:
        out.append(
            CostLine(
                kind="shot.image",
                item_id=shot.id,
                model_id=img_record.id,
                amount=img_cost,
                currency=(
                    img_record.cost_estimate.currency
                    if img_record.cost_estimate
                    else "USD"
                ),
                note="storyboard still",
            )
        )

    if shots_as_video:
        v_record = pick_model(category="image_to_video", quality_tier=quality)
        v_cost = estimate_call_cost(v_record, seconds=duration)
        if v_cost is None:
            skipped.append(f"shot {shot.id} i2v: no cost_estimate on {v_record.id!r}")
        else:
            out.append(
                CostLine(
                    kind="shot.video",
                    item_id=shot.id,
                    model_id=v_record.id,
                    amount=v_cost,
                    currency=(
                        v_record.cost_estimate.currency
                        if v_record.cost_estimate
                        else "USD"
                    ),
                    note=f"image_to_video × {duration:.1f}s",
                )
            )
    return out


def _beat_pricing_lines(
    beat: Beat,
    *,
    speaker_has_voice_clone: bool,
    tts_quality: str,
    lipsync_quality: str,
    estimated_seconds: float | None,
    skipped: list[str],
) -> list[CostLine]:
    if not beat.line:
        return []

    out: list[CostLine] = []
    secs = (
        estimated_seconds
        if estimated_seconds is not None
        else _word_count(beat.line) * 0.4
    )

    tts_category = "voice_clone" if speaker_has_voice_clone else "tts"
    try:
        tts_record = pick_model(category=tts_category, quality_tier=tts_quality)
    except KeyError:
        skipped.append(f"beat {beat.id} tts: no model in category {tts_category!r}")
        return out

    tts_cost = estimate_call_cost(tts_record, seconds=secs)
    if tts_cost is None:
        skipped.append(f"beat {beat.id} tts: no cost_estimate on {tts_record.id!r}")
    else:
        out.append(
            CostLine(
                kind="beat.tts",
                item_id=beat.id,
                model_id=tts_record.id,
                amount=tts_cost,
                currency=(
                    tts_record.cost_estimate.currency
                    if tts_record.cost_estimate
                    else "USD"
                ),
                note=f"~{secs:.1f}s of speech",
            )
        )

    av_record = pick_model(category="avatar", quality_tier=lipsync_quality)
    av_cost = estimate_call_cost(av_record, seconds=secs)
    if av_cost is None:
        skipped.append(f"beat {beat.id} avatar: no cost_estimate on {av_record.id!r}")
    else:
        out.append(
            CostLine(
                kind="beat.avatar",
                item_id=beat.id,
                model_id=av_record.id,
                amount=av_cost,
                currency=(
                    av_record.cost_estimate.currency
                    if av_record.cost_estimate
                    else "USD"
                ),
                note=f"face animation × {secs:.1f}s",
            )
        )

    return out


def estimate_scene_cost(
    scene: Scene,
    *,
    tts_quality: str = "balanced",
    lipsync_quality: str = "high",
    shot_quality: str = "balanced",
    shots_as_video: bool = False,
) -> CostRollup:
    """Estimate the USD cost of a full :func:`render_scene` invocation.

    Walks every shot + beat with the same ``pick_model`` semantics
    the renderer uses, then sums per-call costs. Returns a structured
    :class:`CostRollup` with per-line breakdowns, plus a list of
    "skipped" entries the caller should surface (typically: a model
    with no ``cost_estimate`` populated).
    """
    chars_by_name = {c.name: c for c in scene.characters}
    lines: list[CostLine] = []
    skipped: list[str] = []

    for shot in scene.shots:
        lines.extend(
            _shot_pricing_lines(
                shot,
                style=scene.style,
                shots_as_video=shots_as_video,
                quality=shot_quality,
                skipped=skipped,
            )
        )

    for beat in scene.beats:
        speaker = chars_by_name.get(beat.speaker)
        if speaker is None:
            continue
        cloning = bool(speaker.voice and speaker.voice.reference_audio_url)
        lines.extend(
            _beat_pricing_lines(
                beat,
                speaker_has_voice_clone=cloning,
                tts_quality=tts_quality,
                lipsync_quality=lipsync_quality,
                estimated_seconds=getattr(beat, "duration_s", None),
                skipped=skipped,
            )
        )

    total = sum(ln.amount for ln in lines)
    currency = lines[0].currency if lines else "USD"
    return CostRollup(
        total_amount=total,
        currency=currency,
        lines=tuple(lines),
        skipped=tuple(skipped),
    )


def _word_count(text: str) -> int:
    return len([w for w in text.split() if w])
