"""Audio operations: text-to-speech and friends."""

from __future__ import annotations

from typing import Optional

from ..core import call_fal
from ..registry import pick_model, register_tool
from ..results import Result, parse_response


@register_tool(
    name="text_to_speech",
    description=(
        "Synthesize speech from text. Picks a TTS model by quality tier; "
        "pass `voice` and `extra` for model-specific knobs. Returns a "
        "falai.Result whose .first asset is the audio URL."
    ),
    tags=("audio", "tts", "generate"),
    input_schema={
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "quality": {
                "type": "string",
                "enum": ["fast", "balanced", "high", "ultra"],
                "default": "balanced",
            },
            "voice": {
                "type": "string",
                "description": "Voice identifier; format depends on the model.",
            },
            "model_id": {"type": "string"},
            "extra": {"type": "object"},
        },
    },
    output_schema={"type": "object", "description": "falai.Result"},
    examples=(
        {"text": "Hello world", "quality": "balanced"},
        {"text": "Bonjour le monde", "quality": "high", "voice": "fr-FR-female-1"},
    ),
)
def text_to_speech(
    text: str,
    *,
    quality: str = "balanced",
    voice: Optional[str] = None,
    model_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Result:
    """Synthesize speech. ``voice`` semantics are model-specific."""
    model = model_id or pick_model(category="tts", quality_tier=quality).id
    arguments: dict = {"text": text}
    if voice:
        arguments["voice"] = voice
    arguments.update(extra or {})
    raw = call_fal(model, arguments)
    return parse_response(raw, application=model, arguments=arguments)
