"""Tests for the falaw SKILL.md generator (falaw.bridges.skill)."""

import os

from falaw.bridges.skill import build_skill_md, write_skill_files

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHECKED_IN_SKILL_PATHS = (
    os.path.join(_REPO_ROOT, "falaw", "data", "skills", "falaw", "SKILL.md"),
    os.path.join(_REPO_ROOT, ".claude", "skills", "falaw", "SKILL.md"),
)


def test_skill_includes_registered_tools():
    md = build_skill_md()
    assert "name: falaw" in md
    assert "generate_image" in md
    assert "text_to_speech" in md
    # The journal recipe should appear so agents read+write it.
    assert "journal" in md
    assert "recent(" in md


def test_regen_skill_is_byte_identical_to_checked_in_files(tmp_path):
    """regen-skill must be a no-op on a clean tree (falaw#53, falaw#57).

    The generator is the single source of truth for SKILL.md: every hand-
    written section lives in ``_HEADER``/``_FOOTER_TEMPLATE``, not bolted onto
    the checked-in file after the fact. If this test goes red, someone edited
    a checked-in SKILL.md directly instead of the generator, or vice versa.
    """
    target_dir = tmp_path / "falaw"
    write_skill_files(str(target_dir))
    regenerated = (target_dir / "SKILL.md").read_text()
    for checked_in_path in _CHECKED_IN_SKILL_PATHS:
        with open(checked_in_path) as f:
            checked_in = f.read()
        assert regenerated == checked_in, (
            f"{checked_in_path} has drifted from the generator; "
            "run `python -m falaw regen-skill` and commit the result"
        )
