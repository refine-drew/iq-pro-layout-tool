"""
Round-trip tests for the Laguna IQ ATC .mmg dialect (input + output).

The .mmg files this fork consumes differ from VCarve .nc files: every line is
N##-numbered, there are no (T#=...) tool-definition comments, coordinates are in
mm, and the boot/park sequence is lean (G54 only, no G43/G53). These tests pin
the behaviour that makes such files work end-to-end.
"""
import app as app_module
from app import _parse_file, _seed_part_tools
from collision import PlacedPart
from gcode_generator import generate_master_gcode
from gcode_parser import parse_vcarve_text

# Minimal IQ ATC .mmg: N-numbered, no tool-def comments, mm coordinates.
MMG_SAMPLE = """(VECTRIC POST REVISION)
(0554D5E4E588C610BAB1C5A90DDB2F4D)
N20  (Filename:  TEST)
N30 (Machine:  Laguna IQ ATC)
( Material Size)
( X= 457.200, Y= 304.800, Z= 19.050)
N60 G54
N70 T2 M06
N80 M03 S18000
N90 G00 X243.1647 Y308.8232
N100 G00 Z25.4000
N110 G01 Z14.2875 F1270.0
N120 G01 X15.6587 Y308.0304
N130 G01 X230.4978 Y100.0
N140 G00 Z25.4000
N7510 M05
N7520 M30
%
"""


def test_mmg_parses_without_tool_defs():
    part = parse_vcarve_text(MMG_SAMPLE, filename="TEST.mmg")
    # Material size from the ( X=, Y=, Z=) header.
    assert part.vcarve_x_span == 457.2
    assert part.vcarve_y_span == 304.8
    assert part.material_thickness == 19.05
    # Tool change recognised even though it is N-numbered and has no (T2=...) def.
    assert [p.tool_number for p in part.passes] == ["T2"]
    # No (T#=...) comments → parser leaves tools empty (diameters come from config).
    assert part.tools == {}
    # Z validation may warn (shallow sample) but must not block a valid file.
    assert part.z_validation.status != "blocked"


def test_app_seeds_mmg_tool_diameter_from_config(tmp_path):
    f = tmp_path / "TEST.mmg"
    f.write_text(MMG_SAMPLE, encoding="utf-8")
    part = _parse_file(str(f))
    # config.json defines T2 = 0.5" — backfilled so collision/UI have a diameter.
    assert part.tools["T2"]["diameter_inches"] == 0.5


def test_seed_part_tools_leaves_unknown_tool_unresolved(monkeypatch):
    # A tool not in the library stays without a diameter (so /api/place can prompt).
    monkeypatch.setitem(app_module.config, "tools", {})
    part = parse_vcarve_text(MMG_SAMPLE, filename="TEST.mmg")
    _seed_part_tools(part)
    assert part.tools["T2"].get("diameter_inches") is None


def test_mmg_generates_iq_dialect():
    part = parse_vcarve_text(MMG_SAMPLE, filename="TEST.mmg")
    placed = PlacedPart(part=part, rail="A", slot_inches=0.0, instance_id="t1")
    settings = {
        "job_name": "rt",
        "job_safe_z": {"value": 49.05, "driven_by": "TEST.mmg"},
        "advanced": {"rail_width_mm": 82.55, "bed_x_mm": 609.6,
                     "bed_y_mm": 1371.6, "slots": [0, 13, 26, 39]},
    }
    out = generate_master_gcode([placed], settings)
    lines = out.splitlines()
    # Lean IQ boot: G54 only.
    assert any(l.endswith("G54") for l in lines)
    assert "G71" not in out and "G17" not in out and "G53" not in out and "G43" not in out
    # N-numbered, mm.
    assert any(l.startswith("N10 ") for l in lines)
    # Park: Z retract, M05, M30, then program end.
    assert lines[-1] == "%"
    assert "M30" in lines[-2]
