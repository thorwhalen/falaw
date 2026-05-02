from pyfal.registry import get_model, list_models, list_tools, pick_model


def test_list_models_seeded():
    assert any(m.category == "image" for m in list_models())
    assert any(m.category == "video" for m in list_models())


def test_pick_model_picks_image_fast():
    m = pick_model(category="image", quality_tier="fast")
    assert m.category == "image"
    assert m.quality_tier == "fast"


def test_pick_model_falls_back_when_tier_absent():
    # 'image_edit' category has only 'ultra' in the seed; asking for 'fast'
    # should still return something rather than KeyError.
    m = pick_model(category="image_edit", quality_tier="fast")
    assert m.category == "image_edit"


def test_get_model_alias():
    m = get_model("flux-schnell")
    assert m.id == "fal-ai/flux/schnell"


def test_generate_image_registered():
    names = {t.name for t in list_tools(tag="image")}
    assert "generate_image" in names


def test_text_to_speech_registered():
    names = {t.name for t in list_tools(tag="tts")}
    assert "text_to_speech" in names
