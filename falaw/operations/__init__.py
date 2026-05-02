"""Task-level verbs: stable, agent-friendly entry points.

Each submodule registers its functions via the `register_tool` decorator,
so importing this package populates the ToolRegistry as a side effect.
"""

from .audio import text_to_speech, voice_clone  # noqa: F401
from .avatar import lipsync, talking_avatar_from_text  # noqa: F401
from .images import (  # noqa: F401
    edit_image,
    generate_image,
    remove_background,
    upscale_image,
)
from .video import image_to_video, text_to_video  # noqa: F401
