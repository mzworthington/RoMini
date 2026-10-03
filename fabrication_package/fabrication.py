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
# None on an edge is a straight cut. The bottom of each wall is straight so the base can drop out.
FRONT_EDGES = {"top": True, "right": False, "bottom": None, "left": False}
RIGHT_EDGES = {"top": True, "right": False, "bottom": None, "left": True}
BACK_EDGES = {"top": False, "right": True, "bottom": None, "left": True}
LEFT_EDGES = {"top": False, "right": True, "bottom": None, "left": False}
TOP_EDGES = {
    "top": not BACK_EDGES["top"],
    "right": not RIGHT_EDGES["top"],
    "bottom": not FRONT_EDGES["top"],
    "left": not LEFT_EDGES["top"],
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
    for wall in (FRONT_EDGES, RIGHT_EDGES, BACK_EDGES, LEFT_EDGES):
        if wall["bottom"] is not None:
            raise SystemExit("wall bottom must stay straight so the base can drop out")


def _finger_path(edges: dict[str, bool | None]) -> str:
    width = SIZE / FINGERS

    def runs(male_first: bool | None) -> list[tuple[float, float, float]]:
        if male_first is None:
            return [(0.0, SIZE, 0.0)]
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
    art = lid.split('<g id="ENGRAVE"', 1)[1]
    art = '<g id="ENGRAVE"' + art.split("</svg>", 1)[0]
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
  <desc>One 3.0 mm sheet: TOP FRONT BACK LEFT RIGHT SPEAKER_BACK, a 123 mm BOTTOM that unscrews into dowels, and a 123 mm PI_RISER. Finger joints are 3.0 mm deep. Wall bottoms are straight. Red is through-cut. ENGRAVE is only on TOP. Green circles are drills.</desc>
  <g id="TOP" transform="translate({col[0]:.0f} {row1:.0f})">
    <path d="{_finger_path(TOP_EDGES)}" fill="none" stroke="#e10600" stroke-width="0.2"/>
{lid_art}  </g>
  <g id="BOTTOM" transform="translate({col[1]:.0f} {row1:.0f})">
    <rect x="0" y="0" width="123" height="123" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <g id="PANEL_SCREWS" fill="none" stroke="#00aa00" stroke-width="0.2">
      <circle cx="5.5" cy="5.5" r="1.7"/>
      <circle cx="117.5" cy="5.5" r="1.7"/>
      <circle cx="5.5" cy="117.5" r="1.7"/>
      <circle cx="117.5" cy="117.5" r="1.7"/>
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
  <g id="SPEAKER_BACK" transform="translate({col[2] + 14:.0f} {row2 + 14:.0f})">
    <rect x="0" y="0" width="102" height="102" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <rect x="23" y="22" width="18" height="58" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <rect x="61" y="22" width="18" height="58" fill="none" stroke="#e10600" stroke-width="0.2"/>
  </g>
  <g id="PI_RISER" transform="translate({col[3]:.0f} {row2:.0f})">
    <rect x="0" y="0" width="123" height="123" fill="none" stroke="#e10600" stroke-width="0.2"/>
    <g id="DOWEL_HOLES" fill="none" stroke="#00aa00" stroke-width="0.2">
      <circle cx="5.5" cy="5.5" r="4.2"/>
      <circle cx="117.5" cy="5.5" r="4.2"/>
      <circle cx="5.5" cy="117.5" r="4.2"/>
      <circle cx="117.5" cy="117.5" r="4.2"/>
    </g>
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
ROMINI STORYBOX (130 mm CUBE) — ONE 3.0 mm SHEET
================================================================================

1. STOCK
   - One sheet of 3.0 mm BB/BB Baltic birch.
   - Cut file: 01_Vector_CAD_Files/RoMini_Storybox_3mm_Cube.svg
   - Finished cube: 130.0 x 130.0 x 130.0 mm outside.
   - Sheet2_3mm_BalticBirch_TopLid.svg is the logo master, already placed on TOP. Do not cut it as a separate part.

2. PIECES
   - TOP: finger-jointed lid. Engrave the black artwork about 0.5 mm. Do not engrave a background, and do not cut through the lid. About 2.5 mm of wood remains.
   - BOTTOM: 123 x 123 mm panel. It drops into the 124 mm cavity and unscrews. Four green 3.4 mm holes, 5.5 mm from each corner, are clearance for M3 screws.
   - PI_RISER: 123 x 123 mm shelf. Four green 8.4 mm holes, 5.5 mm from each corner, are clearance for the 8 mm dowels. Glue the shelf about halfway up so the Raspberry Pi sits nearer the NFC hat under the lid. Drill the Pi mounting holes by hand.
   - FRONT: finger joints on the top and sides, straight bottom edge. 16 x 16 grille, 2.8 mm holes on a 5.0 mm pitch.
   - BACK: finger joints on the top and sides, straight bottom edge. 22 mm USB-C hole (centre 25, 105) and 16 mm button hole (centre 105, 105), measured from the panel's top-left.
   - LEFT and RIGHT: finger joints on the top and sides, straight bottom edge.
   - SPEAKER_BACK: 102 x 102 mm baffle behind the grille. Two 18 x 58 mm openings suit the 30 x 70 mm enclosed speakers, with the long side vertical.

3. JOINERY
   - Nine fingers per jointed edge, 3.0 mm deep, matching the stock. The bottom edges of the four walls are straight.
   - Bit: 1/8 in (3.175 mm) downcut. Add R1.6 mm dogbones on the internal finger corners.
   - Red stroke = through-cut. Black fill = engrave. Green stroke = drill.
================================================================================
"""

with open(f"{pkg_dir}/03_Specifications/Technical_Specifications.txt", "w", encoding="utf-8") as spec_file:
    spec_file.write(spec_txt)

# ==============================================================================
# 4. FABRICATION BRIEF / RFQ LETTER TO THE CNC SHOP
# ==============================================================================
rfq_txt = """Subject: CNC Machining RFQ: RoMini Storybox 130 mm cube, one 3 mm sheet

Dear CNC Team,

Please machine the enclosure from a single sheet of 3.0 mm Baltic birch. The cut file is RoMini_Storybox_3mm_Cube.svg. Units are millimetres. The sheet holds the cube, the speaker baffle, and the Pi riser. 

Pieces, top row then bottom row:
- TOP: logo lid. Engrave the black artwork about 0.5 mm. Do not engrave a background, and do not cut through the lid.
- BOTTOM: 123 mm square panel. It unscrews. Four green holes are 3.4 mm clearance for M3 screws, 5.5 mm from each corner.
- FRONT: speaker grille, 256 holes of 2.8 mm. Straight bottom edge.
- BACK: 22 mm USB-C hole and 16 mm button hole. Straight bottom edge.
- LEFT, RIGHT: side walls. Straight bottom edge.
- SPEAKER_BACK: 102 mm square baffle behind the front grille. It fits between the corner dowels. Two rectangles, 18 x 58 mm. Do not drill speaker screw holes.
- PI_RISER: 123 mm square shelf.

Finger joints are 3.0 mm deep, nine per jointed edge. Wall bottoms are straight. Please add R1.6 mm dogbones for a 1/8 in downcut bit.

Sheet2_3mm_BalticBirch_TopLid.svg is the logo master only. Do not cut it as a separate part.

Kind regards,
Design & Engineering Team
"""

with open(f"{pkg_dir}/03_Specifications/CNC_Machining_Brief.txt", "w", encoding="utf-8") as brief_file:
    brief_file.write(rfq_txt)

zip_filename = "RoMini_Storybox_Fabrication_Package.zip"
with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(pkg_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, pkg_dir)
            zipf.write(file_path, arcname)

print(f"Archive successfully generated: {zip_filename}")
