from math import hypot

import pytest
from gcode_parser import (
    parse_vcarve_text, validate_z, GcodePass, extract_file_segments, _arc_points,
)

# --- fixtures ---

SAMPLE_VCARVE = """(VECTRIC POST REVISION)
(hash)
(filename)
(CREATED date)
( Material Size)
( X= 1676.400, Y= 3200.400, Z= 31.877)
(Tools used in this file: )
(T2 = End Mill {0.5 inches})
G00 X0 Y0
G01 X100 Y200
G02 X200 Y300
"""

# Real-file spoilboard-referenced: thin overtravel only
SAMPLE_SPOILBOARD = """( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
(Tools used in this file: )
(T2 = End Mill {0.5 inches})
G43 H2 Z44.4754
T2 M06
G00 X0 Y0
G01 X10 Y10 Z18.796
G01 X50 Y50 Z-0.254
G01 X100 Y100 Z-0.254
G53 G49 Z0
M05
M30
"""

# Legacy top-of-material convention — should be blocked
SAMPLE_LEGACY = """( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
(T2 = End Mill {0.5 inches})
G43 H2 Z25.4254
T2 M06
G00 X0 Y0
G01 X50 Y50 Z-19.304
G53 G49 Z0
M05
M30
"""

# Two-pass file: T2 then T4
SAMPLE_TWO_PASS = """( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
(T2 = End Mill {0.5 inches})
(T4 = Table Stiff {0.75 inches})
G43 H2 Z44.4754
T2 M06
G00 X0 Y0
G01 X50 Y50 Z-0.254
G53 G49 Z0
M05
T4 M06
G00 X0 Y0
G01 X100 Y100 Z-0.254
G53 G49 Z0
M05
M30
"""

# Shallow-cut file (pocket only — warning, not blocked)
SAMPLE_SHALLOW = """( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
(T2 = End Mill {0.5 inches})
G43 H2 Z44.4754
T2 M06
G00 X0 Y0
G01 X50 Y50 Z12.0
G53 G49 Z0
M05
M30
"""

# Safe Z too low — should be blocked
SAMPLE_LOW_SAFE_Z = """( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
(T2 = End Mill {0.5 inches})
G43 H2 Z15.0
T2 M06
G00 X0 Y0
G01 X50 Y50 Z-0.254
G53 G49 Z0
M05
M30
"""

# Missing Material Size header
SAMPLE_NO_HEADER = """(T2 = End Mill {0.5 inches})
G00 X0 Y0
G01 X50 Y50 Z-0.254
M30
"""


# --- existing tests (unchanged) ---

def test_parse_vcarve_text_extracts_blank_and_material():
    part = parse_vcarve_text(SAMPLE_VCARVE, filename="sample.nc")

    assert part.filename == "sample.nc"
    assert part.vcarve_x_span == 1676.4
    assert part.vcarve_y_span == 3200.4
    assert part.material_thickness == 31.877


def test_parse_vcarve_text_extracts_tool_from_header():
    part = parse_vcarve_text(SAMPLE_VCARVE)

    assert "T2" in part.tools
    assert part.tools["T2"]["diameter_inches"] == 0.5


def test_parse_vcarve_text_scans_coordinates():
    part = parse_vcarve_text(SAMPLE_VCARVE)

    assert part.min_vx == 0.0
    assert part.max_vx == 200.0
    assert part.min_vy == 0.0
    assert part.max_vy == 300.0


# --- modal coordinate tests ---

def test_modal_coordinates_carry_y_forward():
    gcode = """( Material Size)
( X= 500, Y= 500, Z= 19.0)
G00 X0 Y10
G01 X100
G01 X200 Y50
"""
    part = parse_vcarve_text(gcode)
    # After G01 X100 (no Y), machine is at (100, 10) — must be included in bbox
    assert part.min_vx == 0.0
    assert part.max_vx == 200.0
    assert part.min_vy == 10.0
    assert part.max_vy == 50.0


def test_modal_coordinates_carry_x_forward():
    gcode = """( Material Size)
( X= 500, Y= 500, Z= 19.0)
G00 X50 Y0
G01 Y100
"""
    part = parse_vcarve_text(gcode)
    # G01 Y100 (no X) — machine moves to (50, 100)
    assert part.min_vx == 50.0
    assert part.max_vx == 50.0
    assert part.min_vy == 0.0
    assert part.max_vy == 100.0


def test_machine_coord_moves_excluded_from_bbox():
    gcode = """( Material Size)
( X= 500, Y= 500, Z= 19.0)
G00 X0 Y0
G01 X100 Y100
G53 X0 Y3048
"""
    part = parse_vcarve_text(gcode)
    # G53 line should not affect bounding box
    assert part.max_vx == 100.0
    assert part.max_vy == 100.0


# --- Z scanning tests ---

def test_z_scan_extracts_min_max_and_safe_z():
    part = parse_vcarve_text(SAMPLE_SPOILBOARD)

    assert part.safe_z == pytest.approx(44.4754)
    assert part.min_z == pytest.approx(-0.254)
    assert part.max_z == pytest.approx(18.796)


def test_z_scan_ignores_g53_lines():
    gcode = """( Material Size)
( X= 500, Y= 500, Z= 19.0)
G43 H2 Z44.0
T2 M06
G01 X10 Y10 Z-0.254
G53 Z0
M30
"""
    part = parse_vcarve_text(gcode)
    # G53 Z0 must not count as a cutting Z — min_z should be -0.254
    assert part.min_z == pytest.approx(-0.254)


def test_z_scan_none_when_no_cutting_z():
    part = parse_vcarve_text(SAMPLE_VCARVE)

    assert part.min_z is None
    assert part.max_z is None


# --- Z validation tests (real-file cases from spec) ---

def test_z_validation_passes_spoilboard_file():
    part = parse_vcarve_text(SAMPLE_SPOILBOARD)

    assert part.z_validation.status == "ok"
    assert part.z_validation.messages == []


def test_z_validation_blocks_legacy_file():
    part = parse_vcarve_text(SAMPLE_LEGACY)

    assert part.z_validation.status == "blocked"
    assert "top-of-material" in part.z_validation.messages[0]


def test_z_validation_blocks_missing_material_header():
    part = parse_vcarve_text(SAMPLE_NO_HEADER)

    assert part.z_validation.status == "blocked"
    assert "Material Size header" in part.z_validation.messages[0]


def test_z_validation_warns_shallow_cut():
    part = parse_vcarve_text(SAMPLE_SHALLOW)

    assert part.z_validation.status == "warning"
    assert "less than half" in part.z_validation.messages[0]


def test_z_validation_blocks_low_safe_z():
    part = parse_vcarve_text(SAMPLE_LOW_SAFE_Z)

    assert part.z_validation.status == "blocked"
    assert "Safe Z height" in part.z_validation.messages[0]


def test_z_validation_no_cutting_z_is_ok():
    # File with no cutting Z values (e.g. only header lines) should not be blocked
    part = parse_vcarve_text(SAMPLE_VCARVE)

    assert part.z_validation.status == "ok"


# --- validate_z unit tests for known real files from spec ---

@pytest.mark.parametrize("material_z,min_z,safe_z,expected_status", [
    (19.05,  -0.254,  44.4754, "ok"),       # 18G.NC
    (50.80,  -0.254,  76.2254, "ok"),       # 24EG.NC
    (19.05,  -0.254,  44.4754, "ok"),       # 24G.NC corrected
    (31.75,   0.000,  57.1754, "ok"),       # 603060-A.NC (no overtravel)
    (19.05, -19.304,  25.4254, "blocked"),  # 24G.NC legacy
    (31.877, -31.877, 25.4254, "blocked"),  # 969034Table.NC legacy
])
def test_z_validation_known_real_files(material_z, min_z, safe_z, expected_status):
    result = validate_z(min_z, safe_z, material_z)
    assert result.status == expected_status


# --- pass extraction tests ---

def test_extract_passes_single_tool():
    part = parse_vcarve_text(SAMPLE_SPOILBOARD)

    assert len(part.passes) == 1
    assert part.passes[0].tool_number == "T2"
    assert part.passes[0].pass_index == 0


def test_extract_passes_two_tools():
    part = parse_vcarve_text(SAMPLE_TWO_PASS)

    assert len(part.passes) == 2
    assert part.passes[0].tool_number == "T2"
    assert part.passes[0].pass_index == 0
    assert part.passes[1].tool_number == "T4"
    assert part.passes[1].pass_index == 1


def test_extract_passes_lines_assigned_correctly():
    part = parse_vcarve_text(SAMPLE_TWO_PASS)

    t2_pass = part.passes[0]
    t4_pass = part.passes[1]

    # Each pass starts with its own T# M06 line
    assert "T2 M06" in t2_pass.lines[0]
    assert "T4 M06" in t4_pass.lines[0]

    # T2 pass should not contain T4 lines
    assert all("T4" not in ln for ln in t2_pass.lines)


def test_extract_passes_empty_when_no_tool_change():
    part = parse_vcarve_text(SAMPLE_VCARVE)

    assert part.passes == []


# --- tool header format tests ---

def _minimal(header_comment):
    return f"( Material Size)\n( X=100, Y=50, Z=19)\n{header_comment}\nT2 M06\nM30\n"


def test_extract_tools_plural_inches_brace():
    part = parse_vcarve_text(_minimal("(T2 = End Mill {0.5 inches})"))
    assert part.tools["T2"]["diameter_inches"] == pytest.approx(0.5)
    assert part.tools["T2"]["description"] == "End Mill {0.5 inches}"


def test_extract_tools_singular_inch_brace():
    part = parse_vcarve_text(_minimal("(T2 = End Mill {0.5 inch})"))
    assert part.tools["T2"]["diameter_inches"] == pytest.approx(0.5)
    assert part.tools["T2"]["description"] == "End Mill {0.5 inch}"


def test_extract_tools_no_brace_dia_suffix():
    part = parse_vcarve_text(_minimal("(T1 = Ball Nose .5 inches Dia)").replace("T2", "T1"))
    assert part.tools["T1"]["diameter_inches"] == pytest.approx(0.5)
    assert part.tools["T1"]["description"] == "Ball Nose .5 inches Dia"


def test_extract_tools_no_diameter_integer_only():
    part = parse_vcarve_text(_minimal("(T5 = ROUNDOVER 125)").replace("T2", "T5"))
    assert part.tools["T5"]["diameter_inches"] is None
    assert part.tools["T5"]["description"] == "ROUNDOVER 125"


def test_extract_tools_description_excludes_tool_prefix():
    part = parse_vcarve_text(_minimal("(T4 = End Mill {.75 inches})").replace("T2", "T4"))
    desc = part.tools["T4"]["description"]
    assert desc == "End Mill {.75 inches}"
    assert "T4" not in desc
    assert "=" not in desc


# --- arc flattening (G02/G03 → line segments for canvas preview) ---

def _chain_is_continuous(segs):
    for a, b in zip(segs, segs[1:]):
        if (a["x2"], a["y2"]) != (b["x1"], b["y1"]):
            return False
    return True


def test_arc_points_r_format_quarter_circle_on_radius():
    # G03 (ccw) quarter circle: (1,0) -> (0,1), R=1, center (0,0).
    pts = _arc_points(1.0, 0.0, 0.0, 1.0, r=1.0, clockwise=False)
    assert len(pts) > 4                       # smoothly subdivided, not a chord
    assert pts[-1] == (0.0, 1.0)              # exact endpoint
    for x, y in pts:
        assert hypot(x, y) == pytest.approx(1.0, abs=1e-9)


def test_arc_points_negative_r_selects_major_arc():
    # Same endpoints, R<0 → the long way around (sweep > pi). The two radius-1
    # circles through (1,0) and (0,1) have centers (0,0) and (1,1); the minor arc
    # rides the (0,0) circle, the major arc rides the (1,1) circle.
    minor = _arc_points(1.0, 0.0, 0.0, 1.0, r=1.0, clockwise=False)
    major = _arc_points(1.0, 0.0, 0.0, 1.0, r=-1.0, clockwise=False)
    assert len(major) > len(minor)            # 270° gets more points than 90°
    for x, y in minor:
        assert hypot(x, y) == pytest.approx(1.0, abs=1e-9)
    for x, y in major:
        assert hypot(x - 1.0, y - 1.0) == pytest.approx(1.0, abs=1e-9)


def test_arc_points_degenerate_r_falls_back_to_chord():
    # R-format can't express a full circle (coincident endpoints) → single chord.
    assert _arc_points(5.0, 5.0, 5.0, 5.0, r=2.0, clockwise=True) == [(5.0, 5.0)]


def _segs(*lines):
    return extract_file_segments([GcodePass(pass_index=0, tool_number="T2", lines=list(lines))])


def test_extract_segments_flattens_arc_into_many_segments():
    segs = _segs("G01 X1 Y0 Z-1", "G03 X0 Y1 R1")
    arc = segs[1:]                            # first seg is the G01 lead-in
    assert len(arc) > 4
    assert _chain_is_continuous(arc)
    assert (arc[0]["x1"], arc[0]["y1"]) == (1.0, 0.0)
    assert (arc[-1]["x2"], arc[-1]["y2"]) == (0.0, 1.0)


def test_extract_segments_linear_move_stays_single_segment():
    segs = _segs("G01 X10 Y20 Z-1")
    assert len(segs) == 1
    assert segs[0]["x2"] == 10.0 and segs[0]["y2"] == 20.0


def test_extract_segments_arc_inherits_missing_axis():
    # Real 18p.nc shape: arc line carries X but no Y → Y inherits current value.
    segs = _segs("G01 X150.8196 Y396.3586 Z-1", "G03 X153.9804 R1.5915")
    arc = segs[1:]
    assert (arc[0]["x1"], arc[0]["y1"]) == pytest.approx((150.8196, 396.3586))
    # End: X overwritten, Y inherited.
    assert (arc[-1]["x2"], arc[-1]["y2"]) == pytest.approx((153.9804, 396.3586))
    assert len(arc) > 1                       # a real curve, not collapsed to a point


def test_extract_segments_full_circle_from_two_semicircles_spans_diameter():
    # Lanyard-hole style: two R-format arcs forming a closed loop, diameter 2.
    segs = _segs("G01 X1 Y0 Z-1", "G03 X-1 Y0 R1", "G03 X1 Y0 R1")
    xs = [s["x1"] for s in segs] + [s["x2"] for s in segs]
    ys = [s["y1"] for s in segs] + [s["y2"] for s in segs]
    assert max(xs) - min(xs) == pytest.approx(2.0, abs=1e-6)
    assert max(ys) - min(ys) == pytest.approx(2.0, abs=1e-6)  # not collapsed flat
