#!/usr/bin/env python3
"""
PackCheck reliability suite.

TRAIN = literature anchors baked into the poured-fill curve (sphere RCP 0.64,
        M&M ellipsoids 0.685, rods AR8 0.467). Reported for transparency.
TEST  = ground truth the engine has never seen:
        - analytic lattice counts (cubes, bricks, cylinders, the M6 nut)
        - published part masses (metcalc M6 nut, Portland Bolt 1/2" nut)
        - measured bulk densities (steel shot, lead shot vendor data)
"""
import json
import numpy as np
import trimesh
from shapely.geometry import Polygon, Point
import packcheck as pc

R = []  # rows: dict(case, kind, predicted, actual, err_pct, note)

def row(case, kind, pred, actual, note="", train=False):
    err = 100.0 * (pred - actual) / actual
    R.append({"case": case, "kind": kind, "predicted": round(pred, 4),
              "actual": round(actual, 4), "err_pct": round(err, 2),
              "train": train, "note": note})
    tag = "TRAIN" if train else "TEST "
    print(f"[{tag}] {case:38s} pred={pred:>10.3f} actual={actual:>10.3f} err={err:+6.2f}%  {note}")

BOX = (100.0, 100.0, 100.0)

# ---------------- G: geometric packing vs analytic ground truth ----------
def g_cases():
    cube = trimesh.creation.box(extents=[10, 10, 10])
    r = pc.placed_pack(cube, BOX, clearance=0.0, angle_step=15)[0]
    row("G1 cubes 10mm in 100mm box", "geometric", r["count"], 1000,
        f'{r["per_layer"]}/layer x {r["layers"]}')

    brick = trimesh.creation.box(extents=[20, 10, 5])
    r = pc.placed_pack(brick, BOX, clearance=0.0, angle_step=15)[0]
    row("G2 bricks 20x10x5 in 100mm box", "geometric", r["count"], 1000,
        f'{r["per_layer"]}/layer x {r["layers"]}')

    cyl = trimesh.creation.cylinder(radius=5, height=10, sections=64)
    r = pc.placed_pack(cyl, BOX, clearance=0.0, angle_step=15)[0]
    # analytic: staggered circles in 100x100: 11 rows (6x10 + 5x9) = 105/layer
    row("G3 cylinders D10xH10 in 100mm box", "geometric", r["count"], 1050,
        f'{r["per_layer"]}/layer x {r["layers"]} (hex-lattice truth 105/layer)')

    nut = pc.load_mesh("nut.stp")
    r = pc.placed_pack(nut, (228.6,) * 3, clearance=0.0, angle_step=15)[0]
    # analytic honeycomb, zero clearance: 572/layer x 45 = 25740 (hand-verified)
    row("G4 M6 nuts in 9in box (0 clearance)", "geometric", r["count"], 25740,
        f'{r["per_layer"]}/layer x {r["layers"]}')

# ---------------- M: part mass vs published data -------------------------
def m_cases():
    nut = pc.load_mesh("nut.stp")
    mass = nut.volume / 1000 * 7.85
    row("M1 M6 nut mass (STEP->mesh, g)", "mass", mass, 2.573,
        "metcalc.info DIN934 2.573 g/pc")

    # parametric 1/2"-13 finished hex nut per ASME B18.2.2:
    # F=3/4" across flats, H=7/16" thick, tap hole ~27/64", 30deg chamfers both faces
    F, H, hole_d = 19.05, 11.11, 10.72
    s = F / np.sqrt(3)
    hexagon = Polygon([(s * np.cos(a), s * np.sin(a))
                       for a in np.pi / 6 + np.arange(6) * np.pi / 3])
    body = trimesh.creation.extrude_polygon(
        hexagon.difference(Point(0, 0).buffer(hole_d / 2, resolution=32)), H)
    vol = body.volume
    # chamfer correction: cones trimmed off both faces outside the circle
    # inscribed at across-flats; standard double-chamfered nut ~ -6% volume
    vol_cham = vol * 0.94
    mass = vol_cham / 1000 * 7.85
    row("M2 1/2in hex nut mass (parametric, g)", "mass", mass, 17.01,
        "Portland Bolt 3.75 lb/100pc")

# ---------------- P: poured fill vs physics/vendor data ------------------
def p_cases():
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=5)
    big = (500.0, 500.0, 500.0)   # bulk limit: wall effect ~ nil

    shaken = pc.poured_estimate(sphere, big, "shaken")
    row("P0 spheres dense fill (train anchor)", "poured",
        shaken["fill_fraction_hulls"], 0.64, "RCP literature", train=True)

    poured = pc.poured_estimate(sphere, big, "poured")
    row("P1 steel shot poured bulk density", "poured",
        poured["fill_fraction_hulls"], 4.4 / 7.85, "vendor 4.4 g/cm3 vs solid 7.85")

    mid = 0.5 * (poured["fill_fraction_hulls"] + shaken["fill_fraction_hulls"])
    row("P2 lead shot settled bulk density", "poured",
        mid, 436 / 62.428 / 11.34, "MarShield 436 lb/ft3 vs solid 11.34; pred=band mid")

    # M&M-proportioned ellipsoid (oblate 1.93:1), dense: Donev et al. 0.685
    mm = trimesh.creation.icosphere(subdivisions=3, radius=5)
    mm.apply_scale([1.0, 1.0, 1 / 1.93])
    r = pc.poured_estimate(mm, big, "shaken")
    row("P3 M&M ellipsoids dense (train anchor)", "poured",
        r["fill_fraction_hulls"], 0.685, "Donev/Chaikin Science 2004", train=True)

    rod = trimesh.creation.cylinder(radius=2.5, height=40, sections=32)  # AR 8
    r = pc.poured_estimate(rod, (400, 400, 400), "shaken")
    row("P4 rods AR8 dense (train anchor)", "poured",
        r["fill_fraction_hulls"], 0.467, "Freeman et al. 2019", train=True)

if __name__ == "__main__":
    print("=" * 100)
    g_cases(); m_cases(); p_cases()
    print("=" * 100)
    test = [abs(r["err_pct"]) for r in R if not r["train"]]
    print(f"TEST cases: {len(test)} | mean |err| = {np.mean(test):.2f}% | "
          f"max |err| = {np.max(test):.2f}%")
    json.dump(R, open("validation.json", "w"), indent=1)
