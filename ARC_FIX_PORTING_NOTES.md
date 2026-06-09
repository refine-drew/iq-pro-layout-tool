# Porting the arc-visualization fix to the parent (`cnc-nest-app`) repo

This fork (IQ Pro Layout Tool) fixed a bug where curved toolpaths (`G02`/`G03`
arcs) rendered on the bed canvas as straight chords — circular cutouts collapsed
to a single near-zero-length point, rounded corners flattened. The same bug
almost certainly exists in the dual-rail parent repo we copied from, because the
broken code lives in `gcode_parser.extract_file_segments()`, which is shared
logic that predates the fork.

This note is everything you need to apply the identical fix there.

---

## Why this ports cleanly (read first)

The fix lives **entirely in `extract_file_segments()`**, which works in **file
coordinates** — *before* any rail/slot/machine transform is applied. The
dual-rail vs single-rail difference only matters downstream (`_transform_segments`
in `app.py`, the generator, `collision.py`). So:

- **Copy the helper and loop change verbatim.** No coordinate-system adjustment
  is needed in the parser.
- The frontend (`bed.js`) and the transform are **unchanged** — they already
  draw whatever line segments the parser hands them. Flattening an arc into many
  short segments upstream makes the curve appear with zero frontend work.
- The generated G-code (`.mmg`/`.nc`) is **untouched** — the generator still sees
  and emits real `G02/G03` arcs. This only affects the *preview* segment list.

Before starting, confirm the parent's `extract_file_segments()` still has the
same shape (a per-line loop that extracts only X/Y/Z and appends one
`{x1,y1,x2,y2,cutting}` dict per move). If it diverged, port the *idea*, not the
exact diff.

---

## The bug

`extract_file_segments()` matched `G00`–`G03` moves but pulled only X/Y/Z
coordinates. For an arc it appended a single straight segment from start to end,
discarding the curvature. (VCarve emits **R-format** arcs — `G02 X.. Y.. R101.6`
— confirmed all-R, zero I/J in our sample/part files.)

## The fix

Flatten each `G02/G03` arc into a chain of short line segments inside the parser.

### 1. Imports + regex (top of `gcode_parser.py`)

Add the math imports and an arc-param regex next to `COORD_PATTERN`:

```python
from math import atan2, ceil, cos, hypot, pi, radians, sin
```

```python
ARC_PARAM_PATTERN = re.compile(r"([IJR])\s*([+-]?\d*\.?\d+)", re.IGNORECASE)
```

### 2. New helper `_arc_points()` (place just above `extract_file_segments`)

```python
def _arc_points(
    x0: float, y0: float, x1: float, y1: float,
    *, r: Optional[float] = None,
    i: Optional[float] = None, j: Optional[float] = None,
    clockwise: bool,
) -> List[Tuple[float, float]]:
    """
    Flatten a G02/G03 arc into interpolated points, EXCLUDING the start and
    INCLUDING the exact end. Returns [(x1, y1)] (a single straight chord) for
    degenerate inputs. Center is taken from I/J when supplied, else derived from
    the chord + radius R. Mirrors the arc geometry in
    runtime_estimator._arc_length (center/radius/sweep via atan2).
    """
    if i is not None or j is not None:
        # I/J form: center is an offset from the start point.
        cx, cy = x0 + (i or 0.0), y0 + (j or 0.0)
        radius = hypot(cx - x0, cy - y0)
        if radius == 0:
            return [(x1, y1)]
    elif r is not None:
        radius = abs(r)
        d = hypot(x1 - x0, y1 - y0)
        # R-format can't express a full circle (d==0), and a zero radius is a no-op.
        if d == 0 or radius == 0:
            return [(x1, y1)]
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # Unit perpendicular to the chord.
        px, py = -(y1 - y0) / d, (x1 - x0) / d
        h = (max(0.0, radius * radius - (d / 2.0) ** 2)) ** 0.5
        cand = [(mx + px * h, my + py * h), (mx - px * h, my - py * h)]
        # Pick the center whose swept angle matches R's sign: R>0 -> minor arc
        # (sweep <= pi), R<0 -> major arc (sweep > pi).
        def _sweep(c):
            a0 = atan2(y0 - c[1], x0 - c[0])
            a1 = atan2(y1 - c[1], x1 - c[0])
            s = (a0 - a1) if clockwise else (a1 - a0)
            while s <= 1e-9:
                s += 2 * pi
            return s
        # R<0 -> major arc (largest sweep); R>0 -> minor arc (smallest sweep).
        cx, cy = max(cand, key=_sweep) if r < 0 else min(cand, key=_sweep)
    else:
        return [(x1, y1)]

    a0 = atan2(y0 - cy, x0 - cx)
    a1 = atan2(y1 - cy, x1 - cx)
    sweep = (a0 - a1) if clockwise else (a1 - a0)
    # Normalize into (0, 2*pi]; a coincident start/end (I/J) is a full circle.
    while sweep <= 1e-9:
        sweep += 2 * pi

    n = min(64, max(2, ceil(sweep / radians(6))))
    direction = -1.0 if clockwise else 1.0
    pts: List[Tuple[float, float]] = []
    for k in range(1, n + 1):
        theta = a0 + direction * sweep * (k / n)
        pts.append((cx + radius * cos(theta), cy + radius * sin(theta)))
    # Force the exact endpoint to avoid rounding drift.
    pts[-1] = (x1, y1)
    return pts
```

### 3. Use it in the move loop of `extract_file_segments()`

Add G2/G3 detectors near the existing `rapid_pat` / `move_pat`:

```python
    g2_pat = re.compile(r"\bG0?2\b", re.IGNORECASE)
    g3_pat = re.compile(r"\bG0?3\b", re.IGNORECASE)
```

Then replace the single `segments.append({...})` block (the part guarded by
`if new_x != cur_x or new_y != cur_y:`) with:

```python
            if new_x != cur_x or new_y != cur_y:
                cutting = (not is_rapid) and (new_z < (material_thickness if material_thickness else 0))
                is_g2 = bool(g2_pat.search(line))
                is_g3 = bool(g3_pat.search(line))
                arc_params: Dict[str, float] = {}
                if is_g2 or is_g3:
                    for p, val in ARC_PARAM_PATTERN.findall(line):
                        arc_params[p.upper()] = float(val)
                if (is_g2 or is_g3) and arc_params:
                    points = _arc_points(
                        cur_x, cur_y, new_x, new_y,
                        r=arc_params.get("R"),
                        i=arc_params.get("I"), j=arc_params.get("J"),
                        clockwise=is_g2,
                    )
                    px, py = cur_x, cur_y
                    for qx, qy in points:
                        segments.append({
                            "x1": px, "y1": py,
                            "x2": qx, "y2": qy,
                            "cutting": cutting,
                        })
                        px, py = qx, qy
                else:
                    segments.append({
                        "x1": cur_x, "y1": cur_y,
                        "x2": new_x, "y2": new_y,
                        "cutting": cutting,
                    })
```

Everything else in the loop (coordinate parsing, modal X/Y inheritance, the
`cur_x, cur_y, cur_z = new_x, new_y, new_z` update) stays as-is.

---

## Gotchas specific to the dual-rail parent

- **`ARC_PARAM_PATTERN` order matters vs `COORD_PATTERN`.** They're separate
  regexes, so no conflict — `COORD_PATTERN` still grabs X/Y/Z, the new one grabs
  I/J/R. Don't merge them.
- **`R` is the dialect in use; I/J is the fallback.** If the parent repo's files
  happen to use I/J arcs, this same code handles them (center = start + I/J,
  coincident endpoints = full circle). No change needed.
- **Arc lines often omit X or Y** (modal — the missing axis inherits the current
  position, e.g. `G03 X153.9804 R1.5915`). The existing loop already inherits
  `new_x/new_y` from `cur_x/cur_y`, so this works unchanged. Keep a test for it.
- **Do NOT touch the dual-rail transform.** `_transform_segments` in the parent's
  `app.py` will have both rail A and rail B paths; leave them alone. They consume
  the flattened segments correctly because the flattening happens in file coords.
- **Reference geometry already exists** in `runtime_estimator._arc_length`
  (center/radius/sweep via `atan2`) — the helper above mirrors it, so behavior
  stays consistent with runtime estimation.

---

## Tests to add (mirror `tests/test_gcode_parser.py`)

Import `extract_file_segments` and `_arc_points`, then cover:

1. **R-format quarter circle on radius** — `_arc_points(1,0, 0,1, r=1, clockwise=False)`:
   `len > 4`, last point `== (0,1)`, every point at distance 1 from origin.
2. **Negative-R selects the major arc** — same endpoints with `r=-1` yields more
   points than `r=1`; major-arc points lie on the *other* radius-1 circle
   (center `(1,1)`), minor-arc points on the origin circle.
3. **Degenerate R** — coincident endpoints with `r` set returns a single chord.
4. **Loop flattens arc into many continuous segments** — `G01` lead-in then
   `G03`: arc sub-segments chain (`seg.x2,y2 == next.x1,y1`), exact start/end.
5. **Linear move unaffected** — a `G01` still yields exactly one segment.
6. **Arc inherits missing axis** — `G03 X.. R..` with no Y inherits current Y.
7. **Full circle from two semicircles spans the diameter** (not collapsed flat).

Run `pytest tests/test_gcode_parser.py`, then the full suite.

> Note: in this fork there is one **pre-existing, unrelated** failure
> (`test_runtime_estimator.py::test_part_runtime_round_trip_via_parser`, about
> tool-change timing) that also fails on a clean tree. Check whether the parent
> has the same so you don't mistake it for a regression from this change.

---

## Verify visually

Run the parent app, place a part with a circular cutout and a rounded-corner
rectangle. The cutout should render as a smooth (near-)circle and the corners as
smooth fillets. Reference commit in this fork: `dca4ba9`
("Flatten G02/G03 arcs in canvas preview segments").
