"""The top plate engraves the app logo, and the fabrication script must not replace it."""

import re
from pathlib import Path

SCRIPT = Path(__file__).parent / "fabrication.py"
LID = (
    Path(__file__).parent
    / "RoMini_Storybox_Fabrication_Package"
    / "01_Vector_CAD_Files"
    / "Sheet2_3mm_BalticBirch_TopLid.svg"
)
CUBE = (
    Path(__file__).parent
    / "RoMini_Storybox_Fabrication_Package"
    / "01_Vector_CAD_Files"
    / "RoMini_Storybox_3mm_Cube.svg"
)
PIECES = ("TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT", "SPEAKER_BACK")


def test_top_plate_uses_the_app_logo():
    """The engraved mark is the vector form of src/romini/assets/logo.svg, not a bitmap."""
    text = LID.read_text(encoding="utf-8")
    assert 'id="app-logo"' in text
    assert "data:image/png" not in text


def test_fabrication_script_does_not_replace_the_extracted_lid():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "sheet2_top_lid_svg" not in source


def test_top_lid_logo_is_a_few_smooth_outlines():
    """A photo trace of the wordmark is a pile of short segments. Engraving wants a few curves."""
    text = LID.read_text(encoding="utf-8")
    engrave = text.split('id="ENGRAVE"', 1)[1]
    for path_data in re.findall(r'\bd="([^"]*)"', engrave):
        assert path_data.count("L") < 12


def test_wordmark_is_six_smooth_letter_outlines():
    """RoMini is six glyph outlines. A raster trace of the letters is a pile of paths on the lower band."""
    text = LID.read_text(encoding="utf-8")
    assert 'id="wordmark"' in text
    word = text.split('id="wordmark"', 1)[1].split("</g>", 1)[0]
    paths = re.findall(r'\bd="([^"]*)"', word)
    assert len(paths) == 6
    for path_data in paths:
        assert "C" in path_data
    character = text.split('id="app-logo"', 1)[1].split('id="wordmark"', 1)[0]
    for origin_y in re.findall(r"translate\([0-9.eE+-]+,([0-9.eE+-]+)\)", character):
        assert float(origin_y) < 520


def test_two_simple_stars_sit_inside_the_rings():
    """Two engraved stars flank the logo in the open wood inside the scored rings."""
    text = LID.read_text(encoding="utf-8")
    engrave = text.split('id="ENGRAVE"', 1)[1]
    stars = re.findall(r'<polygon id="star-(?:left|right)" points="([^"]+)"', engrave)
    assert len(stars) == 2
    ring_x, ring_y, inner_radius = 63.0, 62.6, 47.5
    centroids = []
    for points in stars:
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", points)]
        xs, ys = nums[0::2], nums[1::2]
        assert len(xs) == 10
        for x, y in zip(xs, ys, strict=True):
            assert (x - ring_x) ** 2 + (y - ring_y) ** 2 < (inner_radius - 1.5) ** 2
        centroids.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    left, right = sorted(centroids)
    assert left[0] < 50 and right[0] > 76
    assert left[1] < 50 and right[1] < 50


def test_one_3mm_sheet_holds_the_cube_and_speaker_back():
    """Six jointed faces and the speaker back plate are cut from one 3 mm sheet. The logo stays on TOP."""
    text = CUBE.read_text(encoding="utf-8")
    assert "3.0 mm" in text
    assert "6.0 mm" not in text
    for piece in PIECES:
        assert f'id="{piece}"' in text
    top = text.split('id="TOP"', 1)[1].split('id="BOTTOM"', 1)[0]
    assert 'id="app-logo"' in top
    assert 'id="wordmark"' in top
