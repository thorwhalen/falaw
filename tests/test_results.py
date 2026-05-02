from pyfal.results import parse_response


def test_parse_image_list():
    raw = {
        "images": [
            {
                "url": "http://x/img.png",
                "width": 1024,
                "height": 768,
                "content_type": "image/png",
            }
        ],
        "seed": 42,
    }
    r = parse_response(raw, application="fal-ai/flux/dev", arguments={"prompt": "p"})
    assert len(r.assets) == 1
    a = r.first
    assert a.url == "http://x/img.png"
    assert a.kind == "image"
    assert a.width == 1024
    assert r.raw["seed"] == 42


def test_parse_video_single():
    raw = {"video": {"url": "http://x/v.mp4", "duration": 4.0}}
    r = parse_response(raw, application="fal-ai/veo3", arguments={"prompt": "p"})
    assert r.first.kind == "video"
    assert r.first.duration_s == 4.0


def test_parse_audio_url_string():
    raw = {"audio_url": "http://x/a.mp3"}
    r = parse_response(raw, application="fal-ai/minimax/speech-02-hd", arguments={})
    assert r.first.kind == "audio"
    assert r.first.url == "http://x/a.mp3"
