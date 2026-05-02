"""Image-generation operations."""

from __future__ import annotations

from typing import Optional

from ..core import call_fal
from ..registry import pick_model, register_tool
from ..results import Result, parse_response


@register_tool(
    name="generate_image",
    description=(
        "Generate an image from a text prompt. Picks a sensible FLUX model "
        "based on the requested quality tier ('fast', 'balanced', 'high', "
        "'ultra'). Returns a pyfal.Result whose .first asset has a URL you "
        "can .download(to=...)."
    ),
    tags=("image", "generate"),
    input_schema={
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "quality": {
                "type": "string",
                "enum": ["fast", "balanced", "high", "ultra"],
                "default": "balanced",
            },
            "image_size": {"type": "string", "default": "landscape_4_3"},
            "model_id": {
                "type": "string",
                "description": "Override automatic model selection.",
            },
            "extra": {
                "type": "object",
                "description": "Pass-through keyword args for the underlying model.",
            },
        },
    },
    output_schema={"type": "object", "description": "pyfal.Result"},
    examples=(
        {"prompt": "A red panda eating bamboo", "quality": "fast"},
        {"prompt": "Cinematic portrait, 35mm film", "quality": "ultra"},
    ),
)
def generate_image(
    prompt: str,
    *,
    quality: str = "balanced",
    image_size: str = "landscape_4_3",
    model_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Result:
    """Generate an image from a text prompt.

    Pass ``quality`` to select a tier; pass ``model_id`` to override the
    automatic choice. ``extra`` is forwarded verbatim to the fal model so
    advanced users can set ``num_inference_steps``, ``guidance_scale``, etc.
    """
    model = model_id or pick_model(category="image", quality_tier=quality).id
    arguments = {
        "prompt": prompt,
        "image_size": image_size,
        **(extra or {}),
    }
    raw = call_fal(model, arguments)
    return parse_response(raw, application=model, arguments=arguments)
