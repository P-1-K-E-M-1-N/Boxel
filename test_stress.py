#!/usr/bin/env python3
"""Stress suite: hard real + synthetic parts through the full engine,
with independent layout verification and timing.
(Real parts: git clone --depth 1 https://github.com/prusa3d/Original-Prusa-i3 prusa)"""
import time
import numpy as np
from shapely.geometry import box as sbox
from shapely.affinity import rotate as srot, translate as stran
from scipy.spatial import cKDTree
import packcheck as pc

CAT = "prusa/Printed-Parts/STL/"
CASES = [
    ("x-end-idler",        CAT + "x-end-idler.stl",           (600, 400, 300), 0.5),
    ("x-end-motor",        CAT + "x-end-motor.stl",           (600, 400, 300), 0.5),
    ("fan-shroud",         CAT + "fan-shroud.stl",            (600, 400, 300), 0.5),
    ("extruder-idler",     CAT + "extruder-idler-mmu2s.stl",  (600, 400, 300), 0.5),
    ("fs-lever",           CAT + "fs-lever.stl",              (600, 400, 300), 0.5),
    ("y-rod-holder",       CAT + "y-rod-holder.stl",          (600, 400, 300), 0.5),
    ("spool-holder",       CAT + "Spool-holder.stl",          (600, 400, 300), 0.5),
    ("einsy-hinges",       CAT + "Einsy-hinges.stl",          (600, 400, 300), 0.5),
    ("door handle",        "door_handle.stl",                 (600, 400, 300), 1.0),
    ("window regulator",   "window_regulator.stl",            (1200, 1000, 800), 2.0),
    ("car door shell",     "car_door_shell.stl",              (1200, 1000, 800), 2.0),
]

def verify(mesh, best, box, clearance):
    m = mesh.copy(); m.apply_transform(best["transform"])
    foot = pc._footprint(m, clearance)
    poly = srot(foot, best["lattice"]["angle"], origin="centroid")
    minx, miny, maxx, maxy = poly.bounds
    poly = stran(poly, -(minx + maxx) / 2, -(miny + maxy) / 2)
    pflip = srot(poly, 180, origin=(0, 0))
    sq = sbox(-1e-3, -1e-3, box[0] + 1e-3, box[1] + 1e-3)
    shp = [stran(pflip if f else poly, x, y) for x, y, f in best["centers"]]
    inside = all(sq.contains(g) for g in shp)
    bad = 0
    if len(shp) > 1:
        c = np.array([(x, y) for x, y, f in best["centers"]])
        for i, j in cKDTree(c).query_pairs(2 * max(maxx - minx, maxy - miny)):
            if shp[i].intersection(shp[j]).area > 1e-2:
                bad += 1
    return inside, bad

def run():
    print(f"{'part':20s} {'result':>26s} {'fill':>6s} {'time':>6s}  verify")
    print("-" * 78)
    fails = 0
    for name, path, box, cl in CASES:
        t0 = time.time()
        try:
            mesh = pc.load_mesh(path)
            placed = pc.placed_pack(mesh, box, clearance=cl, angle_step=15)
            dt = time.time() - t0
            if not placed:
                print(f"{name:20s} {'DOES NOT FIT':>26s} {'—':>6s} {dt:5.1f}s  n/a")
                continue
            b = placed[0]
            inside, bad = verify(mesh, b, box, cl)
            fill = b["count"] * mesh.volume / np.prod(box) * 100
            ok = "OK" if (inside and bad == 0) else f"FAIL in={inside} ov={bad}"
            if ok != "OK":
                fails += 1
            print(f"{name:20s} {b['count']:>7,} = {b['per_layer']:>5}/lay x{b['layers']:>3} "
                  f"{fill:5.1f}% {dt:5.1f}s  {ok}  [{b['lattice']['lattice']}@{b['lattice']['angle']:.1f}]")
        except BaseException as e:
            fails += 1
            print(f"{name:20s} CRASH: {type(e).__name__}: {str(e)[:60]}")
    print("-" * 78)
    print(f"failures: {fails}/{len(CASES)}")
    return fails

if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
