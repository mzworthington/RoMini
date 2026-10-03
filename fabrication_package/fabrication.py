# CAD path data and the shop letter are long single lines on purpose.
# ruff: noqa: E501
import os
import zipfile

pkg_dir = "RoMini_Storybox_Fabrication_Package"
os.makedirs(f"{pkg_dir}/01_Vector_CAD_Files", exist_ok=True)
os.makedirs(f"{pkg_dir}/02_Artwork_and_Logos", exist_ok=True)
os.makedirs(f"{pkg_dir}/03_Specifications", exist_ok=True)

# The engraved top art is read from the lid master and placed onto the cube sheet.
# It is not redrawn here:
#   RoMini_Storybox_Fabrication_Package/01_Vector_CAD_Files/Sheet2_3mm_BalticBirch_TopLid.svg
#   RoMini_Storybox_Fabrication_Package/02_Artwork_and_Logos/RoMini_Master_Logo_Exact.svg

# ==============================================================================
# 2. ONE 3.0mm SHEET: SIX CUBE FACES + SPEAKER BACK PLATE
# ==============================================================================
SIZE = 130.0
THICK = 3.0
FINGERS = 9
MARGIN = 8.0
GAP = 6.0

# Clockwise finger phase. True means the first finger on that edge is a tab.
# Odd finger count so a reversed mating edge still meshes when the phase is flipped.
FRONT_EDGES = {"top": True, "right": False, "bottom": True, "left": False}
RIGHT_EDGES = {"top": True, "right": False, "bottom": True, "left": True}
BACK_EDGES = {"top": False, "right": True, "bottom": False, "left": True}
LEFT_EDGES = {"top": False, "right": True, "bottom": False, "left": False}
TOP_EDGES = {
    "top": not BACK_EDGES["top"],
    "right": not RIGHT_EDGES["top"],
    "bottom": not FRONT_EDGES["top"],
    "left": not LEFT_EDGES["top"],
}
BOTTOM_EDGES = {
    "top": not BACK_EDGES["bottom"],
    "right": not RIGHT_EDGES["bottom"],
    "bottom": not FRONT_EDGES["bottom"],
    "left": not LEFT_EDGES["bottom"],
}


def _is_tab(male_first: bool, distance: float) -> bool:
    width = SIZE / FINGERS
    index = min(FINGERS - 1, int(distance / width + 1e-9))
    even = index % 2 == 0
    return even if male_first else not even


def _assert_joint(name: str, male_a: bool, dist_a, male_b: bool, dist_b) -> None:
    width = SIZE / FINGERS
    for step in range(1, 80):
        position = SIZE * step / 80
        if abs(position % width) < 0.08 or abs(position % width - width) < 0.08:
            continue
        tab_a = _is_tab(male_a, dist_a(position))
        tab_b = _is_tab(male_b, dist_b(position))
        if tab_a == tab_b:
            raise SystemExit(f"finger joint {name} does not mesh at {position:.2f}")


def _same(position: float) -> float:
    return position


def _rev(position: float) -> float:
    return SIZE - position


def _check_cube_joints() -> None:
    _assert_joint("front-right", FRONT_EDGES["right"], _rev, RIGHT_EDGES["left"], _same)
    _assert_joint("right-back", RIGHT_EDGES["right"], _rev, BACK_EDGES["left"], _same)
    _assert_joint("back-left", BACK_EDGES["right"], _rev, LEFT_EDGES["left"], _same)
    _assert_joint("left-front", LEFT_EDGES["right"], _rev, FRONT_EDGES["left"], _same)
    _assert_joint("top-front", FRONT_EDGES["top"], _same, TOP_EDGES["bottom"], _rev)
    _assert_joint("top-back", BACK_EDGES["top"], _rev, TOP_EDGES["top"], _same)
    _assert_joint("top-right", RIGHT_EDGES["top"], _same, TOP_EDGES["right"], _rev)
    _assert_joint("top-left", LEFT_EDGES["top"], _rev, TOP_EDGES["left"], _same)
    _assert_joint("bottom-front", FRONT_EDGES["bottom"], _rev, BOTTOM_EDGES["bottom"], _rev)
    _assert_joint("bottom-back", BACK_EDGES["bottom"], _same, BOTTOM_EDGES["top"], _same)
    _assert_joint("bottom-right", RIGHT_EDGES["bottom"], _rev, BOTTOM_EDGES["right"], _rev)
    _assert_joint("bottom-left", LEFT_EDGES["bottom"], _same, BOTTOM_EDGES["left"], _same)


def _finger_path(edges: dict[str, bool]) -> str:
    width = SIZE / FINGERS

    def runs(male_first: bool) -> list[tuple[float, float, float]]:
        steps = []
        for index in range(FINGERS):
            tab = (index % 2 == 0) if male_first else (index % 2 == 1)
            inset = 0.0 if tab else THICK
            steps.append((index * width, (index + 1) * width, inset))
        return steps

    points: list[tuple[float, float]] = []

    def add(x_coord: float, y_coord: float) -> None:
        if points and abs(points[-1][0] - x_coord) < 1e-6 and abs(points[-1][1] - y_coord) < 1e-6:
            return
        points.append((x_coord, y_coord))

    for start, end, inset in runs(edges["top"]):
        add(start, inset)
        add(end, inset)
    for start, end, inset in runs(edges["right"]):
        add(SIZE - inset, start)
        add(SIZE - inset, end)
    for start, end, inset in runs(edges["bottom"]):
        add(SIZE - start, SIZE - inset)
        add(SIZE - end, SIZE - inset)
    for start, end, inset in runs(edges["left"]):
        add(inset, SIZE - start)
        add(inset, SIZE - end)
    return "M " + " L ".join(f"{x_coord:.2f} {y_coord:.2f}" for x_coord, y_coord in points) + " Z"


def _lid_engrave(lid_path: str) -> str:
    lid = open(lid_path, encoding="utf-8").read()
    art = lid.split('<g id="SCORE"', 1)[1]
    art = '<g id="SCORE"' + art.split("</svg>", 1)[0]
    return art.rstrip() + "\n"


_check_cube_joints()

sheet_w = MARGIN * 2 + 4 * SIZE + 3 * GAP
sheet_h = MARGIN * 2 + 2 * SIZE + GAP
row1 = MARGIN
row2 = MARGIN + SIZE + GAP
col = [MARGIN + index * (SIZE + GAP) for index in range(4)]

grille = []
for row in range(16):
    y_coord = 27.5 + (row * 5.0)
    for column in range(16):
        x_coord = 27.5 + (column * 5.0)
        grille.append(f'<circle cx="{x_coord:.1f}" cy="{y_coord:.1f}" r="1.4"/>')
grille_svg = "\n".join(grille)

lid_art = _lid_engrave(f"{pkg_dir}/01_Vector_CAD_Files/Sheet2_3mm_BalticBirch_TopLid.svg")

cube_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_w:.0f}mm" height="{sheet_h:.0f}mm" viewBox="0 0 {sheet_w:.0f} {sheet_h:.0f}">
  <title>RoMini Storybox cube, 3.0 mm Baltic birch, one sheet</title>
  <desc>Seven pieces from one 3.0 mm sheet: TOP BOTTOM FRONT BACK LEFT RIGHT and SPEAKER_BACK. Finger joints are 3.0 mm deep. Red is through-cut. SCORE and ENGRAVE are only on TOP. Green circles on BOTTOM are drill holes for the Pi standoffs.</desc>
  <g id="TOP" transform="translate({col[0]:.0f} {row1:.0f})">
    <path d="{_finger_path(TOP_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
{lid_art}  </g>
  <g id="BOTTOM" transform="translate({col[1]:.0f} {row1:.0f})">
    <path d="{_finger_path(BOTTOM_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <g id="PI_STANDOFFS" fill="none" stroke="#00aa00" stroke-width="0.2">
      <circle cx="36.0" cy="40.5" r="1.35"/>
      <circle cx="94.0" cy="40.5" r="1.35"/>
      <circle cx="36.0" cy="89.5" r="1.35"/>
      <circle cx="94.0" cy="89.5" r="1.35"/>
    </g>
  </g>
  <g id="FRONT" transform="translate({col[2]:.0f} {row1:.0f})">
    <path d="{_finger_path(FRONT_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <g id="SPEAKER_GRILLE" fill="none" stroke="#e10600" stroke-width="0.2">
{grille_svg}
    </g>
  </g>
  <g id="BACK" transform="translate({col[3]:.0f} {row1:.0f})">
    <path d="{_finger_path(BACK_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <circle cx="25" cy="105" r="11" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <circle cx="105" cy="105" r="8" fill="none" stroke="#e10600" stroke-width="0.2"/>
  </g>
  <g id="LEFT" transform="translate({col[0]:.0f} {row2:.0f})">
    <path d="{_finger_path(LEFT_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
  </g>
  <g id="RIGHT" transform="translate({col[1]:.0f} {row2:.0f})">
    <path d="{_finger_path(RIGHT_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
  </g>
  <g id="SPEAKER_BACK" transform="translate({col[2] + 5:.0f} {row2 + 5:.0f})">
    <rect x="0" y="0" width="120" height="120" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <circle cx="60" cy="60" r="36" fill="none" stroke="#e10600" stroke-width="0.2"/>
  </g>
</svg>
"""

cube_path = f"{pkg_dir}/01_Vector_CAD_Files/RoMini_Storybox_3mm_Cube.svg"
with open(cube_path, "w", encoding="utf-8") as cube_file:
    cube_file.write(cube_svg)

old_chassis = f"{pkg_dir}/01_Vector_CAD_Files/Sheet1_6mm_BalticBirch_Chassis.svg"
if os.path.exists(old_chassis):
    os.remove(old_chassis)


# ==============================================================================
# 3. TECHNICAL SPECIFICATIONS & PRODUCTION NOTES
# ==============================================================================
spec_txt = """================================================================================
ROMINI STORYBOX (130mm CUBE) — ONE 3.0 mm SHEET
================================================================================

1. STOCK
   - One sheet of 3.0 mm BB/BB Baltic birch.
   - Cut file: 01_Vector_CAD_Files/RoMini_Storybox_3mm_Cube.svg
   - Finished cube: 130.0 x 130.0 x 130.0 mm outside.
   - Do not cut Sheet2 on its own. That drawing is the logo master, already placed on TOP.

2. SEVEN PIECES
   - TOP: finger-jointed lid. SCORE is the three rings (about 0.2 mm). ENGRAVE is the logo (about 0.5 mm). Do not engrave a background. About 2.5 mm of wood remains under the engrave.
   - BOTTOM: finger-jointed base. Four green circles are 2.7 mm drills for M2.5 Pi standoffs on a 58 x 49 mm grid.
   - FRONT: finger-jointed speaker face. 16x16 grille, 2.8 mm holes on a 5.0 mm pitch.
   - BACK: finger-jointed rear. 22 mm USB-C hole (centre 25, 105) and 16 mm button hole (centre 105, 105), measured from the panel's top-left.
   - LEFT and RIGHT: finger-jointed side walls.
   - SPEAKER_BACK: 120 x 120 mm insert that sits behind the grille inside the 124 mm cavity. 72 mm round opening in the centre.

3. JOINERY
   - Nine fingers per edge, 3.0 mm deep, so the joint matches the 3.0 mm stock.
   - Bit: 1/8 in (3.175 mm) downcut. Add R1.6 mm dogbones on the internal finger corners.
   - Red stroke = through-cut. Blue stroke = score. Black fill = engrave. Green stroke = drill.
================================================================================
"""

with open(f"{pkg_dir}/03_Specifications/Technical_Specifications.txt", "w", encoding="utf-8") as spec_file:
    spec_file.write(spec_txt)

# ==============================================================================
# 4. FABRICATION BRIEF / RFQ LETTER TO THE CNC SHOP
# ==============================================================================
rfq_txt = """Subject: CNC Machining RFQ: RoMini Storybox 130mm cube, one 3mm sheet

Dear CNC Team,

Please machine the enclosure from a single sheet of 3.0 mm Baltic birch. The cut file is RoMini_Storybox_3mm_Cube.svg (units are millimetres). It holds all seven pieces.

Pieces, top row then bottom row:
- TOP: logo lid. Score the blue rings about 0.2 mm. Engrave the black artwork about 0.5 mm. Do not engrave a background.
- BOTTOM: base, with four green drill holes for the Pi standoffs.
- FRONT: speaker grille, 256 holes of 2.8 mm.
- BACK: 22 mm USB-C hole and 16 mm button hole.
- LEFT, RIGHT: plain side walls.
- SPEAKER_BACK: 120 mm square insert with a 72 mm round opening. It sits behind the front grille.

Finger joints are 3.0 mm deep (nine per edge). Please add R1.6 mm dogbones for a 1/8 in downcut bit.

Sheet2_3mm_BalticBirch_TopLid.svg is the logo master only. Do not cut it as a separate part.

Kind regards,
Design & Engineering Team
"""

with open(f"{pkg_dir}/03_Specifications/CNC_Machining_Brief.txt", "w", encoding="utf-8") as brief_file:
    brief_file.write(rfq_txt)

# ==============================================================================
# 5. ZIP ARCHIVE COMPRESSION
# ==============================================================================
zip_filename = "RoMini_Storybox_Fabrication_Package.zip"
with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(pkg_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, pkg_dir)
            zipf.write(file_path, arcname)

print(f"Archive successfully generated: {zip_filename}")
