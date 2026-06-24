from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "render" / "assets" / "fonts"


def test_montserrat_fonts_present_and_loadable():
    for name in ("Montserrat-Bold.ttf", "Montserrat-Medium.ttf",
                 "Montserrat-Regular.ttf"):
        path = FONT_DIR / name
        assert path.exists(), f"missing font: {path}"
        # PIL must be able to load it at a real size.
        font = ImageFont.truetype(str(path), 36)
        assert font.getlength("test") > 0
