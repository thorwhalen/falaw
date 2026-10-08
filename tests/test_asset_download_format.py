"""Asset.download vs. content format (falaw#78): SVG under .png, and PNG."""

import warnings

import pytest

from falaw import content
from falaw.results import Asset, sniff_extension

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
SVG = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'


@pytest.fixture
def serve(monkeypatch):
    def _serve(data):
        monkeypatch.setattr(content, "_DEFAULT_FETCHER", lambda url: [data])

    return _serve


def test_sniff():
    assert sniff_extension(PNG) == ".png"
    assert sniff_extension(SVG) == ".svg"
    assert sniff_extension(b"<svg/>") == ".svg"
    assert sniff_extension(b"junk") == ""


def test_svg_under_png_name_warns(serve, tmp_path):
    serve(SVG)
    with pytest.warns(UserWarning, match="svg"):
        path = Asset(url="u", kind="image").download(to=str(tmp_path / "x.png"))
    assert path.endswith("x.png")


def test_svg_fix_suffix(serve, tmp_path):
    serve(SVG)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        path = Asset(url="u", kind="image").download(
            to=str(tmp_path / "x.png"), fix_suffix=True
        )
    assert path.endswith("x.svg")
    assert open(path, "rb").read() == SVG


def test_png_under_png_name_is_silent(serve, tmp_path):
    serve(PNG)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        path = Asset(url="u", kind="image").download(to=str(tmp_path / "x.png"))
    assert open(path, "rb").read() == PNG
