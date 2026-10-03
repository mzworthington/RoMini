"""The top plate engraves the supplied logo, and the fabrication script must not replace it."""

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
SOURCE = Path("/Users/worthington/Documents/RoMini.svg")
PIECES = ("TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT", "SPEAKER_BACK")
RING = "M292.82,0C131.1,0,0,131.1,0,292.82"


def test_top_plate_uses_the_supplied_logo():
    """The lid engraving is the path data from RoMini.svg, copied unchanged."""
    text = LID.read_text(encoding="utf-8")
    source = SOURCE.read_text(encoding="utf-8")
    assert 'id="app-logo"' in text
    assert "data:image/png" not in text
    paths = re.findall(r'\bd="([^"]*)"', source)
    assert len(paths) == 12
    for path_data in paths:
        assert path_data in text
    for points in re.findall(r'\bpoints="([^"]*)"', source):
        assert points in text


def test_fabrication_script_does_not_replace_the_extracted_lid():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "sheet2_top_lid_svg" not in source


def test_top_lid_logo_is_a_few_smooth_outlines():
    """A photo trace of the wordmark is a pile of short segments. Engraving wants a few curves."""
    text = LID.read_text(encoding="utf-8")
    engrave = text.split('id="ENGRAVE"', 1)[1]
    for path_data in re.findall(r'\bd="([^"]*)"', engrave):
        assert path_data.count("L") < 12


def test_lid_keeps_the_engraved_ring_and_drops_the_scored_rings():
    """The black logo ring stays. The three blue score rings are gone."""
    lid = LID.read_text(encoding="utf-8")
    cube = CUBE.read_text(encoding="utf-8")
    for text in (lid, cube):
        assert 'id="SCORE"' not in text
        assert 'r="47.50"' not in text
        assert RING in text


def test_wordmark_is_the_supplied_lettering():
    """RoMini is the letter paths from RoMini.svg."""
    text = LID.read_text(encoding="utf-8")
    assert "M227.93,506.18" in text
    assert 'id="wordmark"' not in text


def test_stars_belong_to_the_supplied_mark():
    """The sparkles are the polygons from RoMini.svg."""
    text = LID.read_text(encoding="utf-8")
    assert "112.02 133.97 126.09 117.56" in text
    assert 'id="star-left"' not in text


def test_bottom_panel_unscrews_to_reach_the_electronics():
    """The base drops out and M3 screws go into dowels glued from the lid down to the opening."""
    text = CUBE.read_text(encoding="utf-8")
    bottom = text.split('id="BOTTOM"', 1)[1].split('id="FRONT"', 1)[0]
    assert 'width="123"' in bottom and 'height="123"' in bottom
    screws = bottom.split('id="PANEL_SCREWS"', 1)[1].split("</g>", 1)[0]
    holes = re.findall(r'cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', screws)
    assert holes == [
        ("5.5", "5.5", "1.7"),
        ("117.5", "5.5", "1.7"),
        ("5.5", "117.5", "1.7"),
        ("117.5", "117.5", "1.7"),
    ]
    assert 'id="CORNER_BLOCKS"' not in text
    assert 'id="PI_STANDOFFS"' not in text
    for piece, nxt in (("FRONT", "BACK"), ("BACK", "LEFT"), ("LEFT", "RIGHT"), ("RIGHT", "SPEAKER_BACK")):
        group = text.split(f'id="{piece}"', 1)[1].split(f'id="{nxt}"', 1)[0]
        outline = re.search(r'\bd="([^"]+)"', group).group(1)
        nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", outline)]
        assert not any(abs(y - 127.0) < 0.05 for y in nums[1::2])
    spec = (
        Path(__file__).parent
        / "RoMini_Storybox_Fabrication_Package"
        / "03_Specifications"
        / "Technical_Specifications.txt"
    ).read_text(encoding="utf-8")
    assert "unscrews" in spec
    assert "dowel" in spec
    assert "M3" in spec
    assert "standoff" not in spec


def test_pi_riser_slides_onto_the_dowels_nearer_the_nfc_hat():
    """A 123 mm shelf slides onto the corner dowels so the Pi can sit nearer the NFC hat."""
    text = CUBE.read_text(encoding="utf-8")
    riser = text.split('id="PI_RISER"', 1)[1]
    assert 'width="123"' in riser and 'height="123"' in riser
    holes = re.findall(r'cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', riser)
    assert holes == [
        ("5.5", "5.5", "4.2"),
        ("117.5", "5.5", "4.2"),
        ("5.5", "117.5", "4.2"),
        ("117.5", "117.5", "4.2"),
    ]
    spec = (
        Path(__file__).parent
        / "RoMini_Storybox_Fabrication_Package"
        / "03_Specifications"
        / "Technical_Specifications.txt"
    ).read_text(encoding="utf-8")
    assert "halfway" in spec
    assert "NFC" in spec


def test_speaker_back_fits_between_the_dowels_with_two_speaker_openings():
    """The baffle clears the corner dowels and has one rectangle for each 30 x 70 mm speaker."""
    text = CUBE.read_text(encoding="utf-8")
    panel = text.split('id="SPEAKER_BACK"', 1)[1].split('id="PI_RISER"', 1)[0]
    assert 'width="102"' in panel and 'height="102"' in panel
    assert 'r="36"' not in panel
    openings = re.findall(r'<rect x="[\d.]+" y="[\d.]+" width="18" height="58"', panel)
    assert len(openings) == 2
    assert 'id="SPEAKER_MOUNTS"' not in panel
    spec = (
        Path(__file__).parent
        / "RoMini_Storybox_Fabrication_Package"
        / "03_Specifications"
        / "Technical_Specifications.txt"
    ).read_text(encoding="utf-8")
    assert "72 mm" not in spec
    assert "30 x 70" in spec


def test_shop_notes_match_the_current_sheet():
    """The shop letter describes this sheet, and the engrave stays a shallow pocket."""
    spec = (
        Path(__file__).parent
        / "RoMini_Storybox_Fabrication_Package"
        / "03_Specifications"
        / "Technical_Specifications.txt"
    ).read_text(encoding="utf-8")
    brief = (
        Path(__file__).parent / "RoMini_Storybox_Fabrication_Package" / "03_Specifications" / "CNC_Machining_Brief.txt"
    ).read_text(encoding="utf-8")
    assert "120 mm" not in spec
    assert "inside face of the bottom panel" in spec
    assert "do not cut through the lid" in brief


def test_fabrication_docs_show_the_sheet():
    """The cube drawing has a docs page and a rendered sheet image."""
    page = Path(__file__).resolve().parents[1] / "docs" / "fabrication.md"
    text = page.read_text(encoding="utf-8")
    assert "RoMini_Storybox_3mm_Cube.svg" in text
    assert "0.5 mm" in text
    sheet = Path(__file__).resolve().parents[1] / "docs" / "images" / "fabrication" / "sheet.png"
    assert sheet.is_file() and sheet.stat().st_size > 1000


def test_one_3mm_sheet_holds_the_cube_and_speaker_back():
    """The cube faces and the speaker back plate are cut from one 3 mm sheet. The logo stays on TOP."""
    text = CUBE.read_text(encoding="utf-8")
    assert "3.0 mm" in text
    assert "6.0 mm" not in text
    for piece in PIECES:
        assert f'id="{piece}"' in text
    top = text.split('id="TOP"', 1)[1].split('id="BOTTOM"', 1)[0]
    assert 'id="app-logo"' in top
    assert RING in top
