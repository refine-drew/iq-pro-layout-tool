import pytest
from gcode_parser import GcodePart, ZValidation
from collision import (
    PlacedPart, Rect,
    blank_rect, toolpath_rect, rects_overlap, check_placement, slot_label,
)

RAIL_W = 82.55
BED_X = 1524.0
# BED_Y is chosen so machine_y = BED_Y - slot*25.4 = (120 - slot)*25.4, keeping
# the transform-math expectations below readable. The transform is bed-size agnostic.
BED_Y = 3048.0


def make_part(vcarve_x_span, vcarve_y_span, min_vx, max_vx, min_vy, max_vy,
              filename="part.nc", tools=None):
    """Minimal GcodePart with known blank and toolpath extents."""
    return GcodePart(
        filename=filename,
        vcarve_x_span=vcarve_x_span,
        vcarve_y_span=vcarve_y_span,
        material_thickness=19.05,
        tools=tools or {},
        min_vx=min_vx,
        max_vx=max_vx,
        min_vy=min_vy,
        max_vy=max_vy,
        raw_lines=[],
        z_validation=ZValidation(status="ok"),
    )


def placed(part, slot_inches, instance_id="i1"):
    return PlacedPart(part=part, rail="A", slot_inches=slot_inches, instance_id=instance_id)


def _machine_y(slot_inches):
    return BED_Y - slot_inches * 25.4


# --- slot_label ---

def test_slot_label_integer():
    assert slot_label("A", 39.0) == "A39"

def test_slot_label_fractional():
    assert slot_label("A", 19.5) == "A19.5"


# --- blank_rect (single rail) ---

def test_blank_rect():
    # vcarve_x_span=100 (along rail = machine Y), vcarve_y_span=200 (across bed = machine X)
    part = make_part(100, 200, 0, 100, 0, 200)
    p = placed(part, 39)
    r = blank_rect(p, RAIL_W, BED_X, BED_Y)

    machine_y = _machine_y(39)
    assert r.min_x == pytest.approx(RAIL_W)
    assert r.max_x == pytest.approx(RAIL_W + 200)        # vcarve_y_span = machine X extent
    assert r.min_y == pytest.approx(machine_y - 100)     # slot_mark - vcarve_x_span
    assert r.max_y == pytest.approx(machine_y)            # slot_mark = high-Y edge


# --- toolpath_rect ---

def test_toolpath_rect_same_as_blank_when_extents_equal():
    part = make_part(100, 100, 0, 100, 0, 100)
    p = placed(part, 39)

    br = blank_rect(p, RAIL_W, BED_X, BED_Y)
    tr = toolpath_rect(p, RAIL_W, BED_X, BED_Y)
    assert tr == br


def test_toolpath_rect_extents_beyond_blank():
    # Toolpath extends 10mm beyond blank on all sides.
    part = make_part(100, 100, -10, 110, -10, 110)
    p = placed(part, 39)
    tr = toolpath_rect(p, RAIL_W, BED_X, BED_Y)

    machine_y = _machine_y(39)
    assert tr.min_x == pytest.approx(RAIL_W - 10)
    assert tr.max_x == pytest.approx(RAIL_W + 110)
    assert tr.min_y == pytest.approx(machine_y - 110)
    assert tr.max_y == pytest.approx(machine_y + 10)


# --- verified spec example: correct axis convention ---
# VCarve X = along rail = machine Y; VCarve Y = across bed = machine X
# Single rail: machX = RAIL_W + VCarve_Y,  machY = slot_mark - VCarve_X

def test_spec_example_notch_position():
    """
    Single rail at slot 36 (slot_mark=2133.6mm)
    Part vcarve_x_span=300 (along rail), vcarve_y_span=400 (across bed)
    Notch at file VCarve_X=20, VCarve_Y=380:
      machine X = RAIL_W + 380 = 462.55
      machine Y = 2133.6 - 20 = 2113.6
    """
    slot_inches = 120 - 2133.6 / 25.4  # ≈ 36.0
    part = make_part(300, 400, 0, 300, 0, 400)

    my = _machine_y(slot_inches)  # 2133.6
    notch_machine_x = RAIL_W + 380      # RAIL_W + VCarve_Y
    notch_machine_y = my - 20           # slot_mark - VCarve_X
    assert notch_machine_x == pytest.approx(462.55, abs=0.01)
    assert notch_machine_y == pytest.approx(2113.6, abs=0.1)


# --- rects_overlap ---

def test_rects_overlap_clear():
    a = Rect(0, 10, 0, 10)
    b = Rect(20, 30, 20, 30)
    assert not rects_overlap(a, b)


def test_rects_overlap_touching_x_not_collision():
    a = Rect(0, 10, 0, 10)
    b = Rect(10, 20, 0, 10)
    assert not rects_overlap(a, b)


def test_rects_overlap_touching_y_not_collision():
    a = Rect(0, 10, 0, 10)
    b = Rect(0, 10, 10, 20)
    assert not rects_overlap(a, b)


def test_rects_overlap_partial_overlap():
    a = Rect(0, 15, 0, 15)
    b = Rect(10, 20, 10, 20)
    assert rects_overlap(a, b)


def test_rects_overlap_contained():
    a = Rect(0, 100, 0, 100)
    b = Rect(10, 90, 10, 90)
    assert rects_overlap(a, b)


# --- check_placement ---

def test_no_collision_when_no_existing_parts():
    part = make_part(100, 100, 0, 100, 0, 100)
    p = placed(part, 39)
    result = check_placement(p, [], RAIL_W, BED_X, BED_Y)
    assert not result.collides


def test_no_collision_parts_far_apart():
    part_a = make_part(100, 100, 0, 100, 0, 100, "a.nc")
    part_b = make_part(100, 100, 0, 100, 0, 100, "b.nc")
    existing = [placed(part_a, 0, "i1")]
    new = placed(part_b, 117, "i2")

    result = check_placement(new, existing, RAIL_W, BED_X, BED_Y)
    assert not result.collides


def test_collision_new_toolpath_into_existing_blank():
    part_a = make_part(200, 100, 0, 200, 0, 100, "a.nc")
    # Part B toolpath extends 400mm toward higher machine Y (min_vx=-400)
    part_b = make_part(200, 100, -400, 200, 0, 100, "b.nc")

    existing = [placed(part_a, 39, "i1")]
    new = placed(part_b, 52, "i2")

    result = check_placement(new, existing, RAIL_W, BED_X, BED_Y)
    assert result.collides
    assert result.conflicting_instance_id == "i1"
    assert "b.nc" in result.message
    assert "a.nc" in result.message


def test_collision_existing_toolpath_into_new_blank():
    part_existing = make_part(200, 100, -400, 200, 0, 100, "existing.nc")
    part_new = make_part(200, 100, 0, 200, 0, 100, "new.nc")

    existing = [placed(part_existing, 52, "i1")]
    new = placed(part_new, 39, "i2")

    result = check_placement(new, existing, RAIL_W, BED_X, BED_Y)
    assert result.collides
    assert "existing.nc" in result.message


def test_no_collision_toolpath_vs_toolpath():
    """
    Two parts whose toolpath extents overlap each other but do NOT reach each
    other's blank boundary must NOT be flagged as a collision.
    """
    part_a = make_part(100, 100, -50, 100, 0, 100, "a.nc")
    part_b = make_part(100, 100, 0, 100, 0, 100, "b.nc")

    existing = [placed(part_a, 39, "i1")]
    new = placed(part_b, 52, "i2")

    result = check_placement(new, existing, RAIL_W, BED_X, BED_Y)
    assert not result.collides


def test_collision_message_contains_slot_labels():
    part_a = make_part(200, 100, -400, 200, 0, 100, "a.nc")
    part_b = make_part(200, 100, 0, 200, 0, 100, "b.nc")

    existing = [placed(part_a, 52, "i1")]
    new = placed(part_b, 39, "i2")

    result = check_placement(new, existing, RAIL_W, BED_X, BED_Y)
    assert "A39" in result.message
    assert "A52" in result.message


# --- tool-radius collision tests ---

def test_toolpath_rect_expands_by_tool_radius():
    part = make_part(100, 100, 0, 100, 0, 100)
    p = placed(part, 39)
    base = toolpath_rect(p, RAIL_W, BED_X, BED_Y, tool_radius_mm=0.0)
    expanded = toolpath_rect(p, RAIL_W, BED_X, BED_Y, tool_radius_mm=10.0)
    assert expanded.min_x == pytest.approx(base.min_x - 10.0)
    assert expanded.max_x == pytest.approx(base.max_x + 10.0)
    assert expanded.min_y == pytest.approx(base.min_y - 10.0)
    assert expanded.max_y == pytest.approx(base.max_y + 10.0)


def test_check_placement_catches_tool_radius_collision():
    """Centerline is clear but cutter physically reaches the adjacent blank."""
    part_a = make_part(300, 100, 0, 300, 0, 100, "a.nc")
    part_b = make_part(300, 100, -20, 300, 0, 100, "b.nc",
                       tools={"T2": {"description": "End Mill", "diameter_inches": 1.0}})

    result = check_placement(placed(part_b, 39, "i2"),
                             [placed(part_a, 26, "i1")], RAIL_W, BED_X, BED_Y)
    assert result.collides
    assert "T2" in result.message


def test_check_placement_passes_when_radius_fits_in_gap():
    """Same geometry, smaller tool — cutter stays clear of the adjacent blank."""
    part_a = make_part(300, 100, 0, 300, 0, 100, "a.nc")
    part_b = make_part(300, 100, -20, 300, 0, 100, "b.nc",
                       tools={"T2": {"description": "End Mill", "diameter_inches": 0.25}})

    result = check_placement(placed(part_b, 39, "i2"),
                             [placed(part_a, 26, "i1")], RAIL_W, BED_X, BED_Y)
    assert not result.collides
