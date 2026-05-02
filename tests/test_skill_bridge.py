from pyfal.bridges.skill import build_skill_md


def test_skill_includes_registered_tools():
    md = build_skill_md()
    assert "name: pyfal" in md
    assert "generate_image" in md
    assert "text_to_speech" in md
    # The journal recipe should appear so agents read+write it.
    assert "journal" in md
    assert "recent(" in md
