# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

IQ Pro Layout Tool is a Flask web app for optimizing CNC cutting layouts on a **single-rail 54×24 in bed** (Laguna IQ ATC machine). It is a disposable fork of the dual-rail `cnc-nest-app` (see the README banner). Users load VCarve/`.MMG` G-code files from a library folder, drag-place parts onto the single rail's 13"-pitch slots, get live collision detection, then generate a merged master `.mmg` file that combines all parts using order-of-operations (grouping cuts by tool across all parts).

## Commands

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run (dev server on http://localhost:5000)
python app.py

# Tests
pytest                        # full suite
pytest tests/test_parser.py   # single file
pytest -k "test_collision"    # single test by name
```

No build step, linter, or type checker is configured.

## Architecture

### Backend (Python/Flask)

**`app.py`** — all Flask routes and in-memory application state:
- `_loaded`: dict of parsed parts (filename → `GcodePart`)
- `_placements`: dict of placed parts (placement ID → placement dict with rail, slot, transforms)
- `_instance_counts`: tracks how many times each part has been placed (for unique IDs)
- Key API routes: `/api/load-library`, `/api/place`, `/api/remove-placement`, `/api/generate`, `/api/save-job`, `/api/load-job`

**`gcode_parser.py`** — parses `.nc`/`.mmg` VCarve G-code files into `GcodePart` dataclasses. Extracts blank dimensions, material thickness, tool info, XYZ bounding boxes per pass, and validates Z depths.

**`collision.py`** — rectangle overlap collision detection. The single rail uses additive XY offsets from the slot mark (see Coordinate Systems below).

**`gcode_generator.py`** — merges placed parts into a single master G-code. Walks tool passes in order-of-operations sequence (all T1 cuts across all parts, then all T2, etc.), applies coordinate transforms matching `collision.py`, and uses nearest-neighbor sorting to minimize rapid travel.

**`tool_library.py`** — simple tool registry. Resolves tool diameters from file headers or user-supplied overrides.

**`config.py`** — loads/saves `config.json`. Config defines library path, output path, tool definitions, bed dimensions (609.6×1371.6 mm / 24×54 in; `bed_y_mm` is the along-rail axis), rail width, safe Z, and slot positions (`[0, 13, 26, 39]` in, 13" pitch).

### Frontend (Vanilla JS + Canvas)

No framework, no bundler. Files in `/static/`:

- **`bed.js`** — HTML5 Canvas renderer. Draws the bed, rails, slots, placed parts with color coding, and ghost preview during drag. This is the largest and most complex frontend file.
- **`sidebar.js`** — library tree (left) and placement tray (right) UI
- **`placement.js`** — drag-and-drop placement logic, communicates with `/api/place`
- **`job.js`** — save/load job state (`.cnj` JSON format)
- **`config.js`** — settings panel, reads/writes `/api/config`

### Data Flow

1. User picks library folder → `/api/load-library` → `gcode_parser` → populates `_loaded` → sidebar tree
2. User drags part to bed slot → `/api/place` → `collision.py` validates → adds to `_placements` → bed canvas redraws
3. User clicks Generate → `/api/generate` → `gcode_generator` merges all `_placements` → writes `.mmg` + `.pdf` report
4. Save/load state persists `_placements` + `_loaded` as a `.cnj` JSON file

### Coordinate Systems

VCarve file axes map to machine axes with the file X axis mirrored (a proper 180°-class
rotation, det(Jacobian) = +1):
- file_X → machine Y (along the rail): `machine_Y = slot_mark - file_X`, where
  `slot_mark = bed_y_mm - (slot_inches + edge_margin_in) * 25.4`
- file_Y → machine X (across the bed): `machine_X = rail_width_mm + file_Y` — additive

`collision.py` (`_machine_y`, `blank_rect`, `toolpath_rect`), `app.py` (`_transform_segments`),
and `gcode_generator.py` (`_transform_params`) must apply identical transforms, or placements
will collide in reality but not in simulation. The internal rail id is always `"A"` (the dual-rail
B path was removed in this fork).
